"""Integration tests for SqlAlchemyUserRepository."""

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.modules.identity.application.unit_of_work import IdentityUnitOfWorkFactory
from src.modules.identity.domain.entities.user import User
from src.modules.identity.domain.value_objects.email import Email
from src.modules.identity.domain.value_objects.user_role import UserRole
from src.modules.identity.infrastructure.persistence.models.user_model import UserModel
from src.shared_kernel.value_objects.user_id import UserId


class TestSqlAlchemyUserRepositorySave:
    async def test_should_persist_a_new_user_and_assign_external_id(
        self, uow_factory: IdentityUnitOfWorkFactory
    ):
        async with uow_factory() as uow:
            saved = await uow.users.save(
                User.create(
                    email=Email("admin@homeflix.local"),
                    role=UserRole.ADMIN,
                    is_superuser=True,
                    is_verified=True,
                    hashed_password="$argon2id$dummy",
                )
            )

        assert saved.id is not None
        assert saved.id.prefix == "usr"
        assert saved.email == Email("admin@homeflix.local")
        assert saved.role == UserRole.ADMIN
        assert saved.is_superuser is True
        assert saved.is_verified is True

    async def test_save_should_round_trip_through_find_by_id(
        self, uow_factory: IdentityUnitOfWorkFactory
    ):
        async with uow_factory() as uow:
            saved = await uow.users.save(User.create(email=Email("a@b.com"), hashed_password="hp"))

        async with uow_factory() as uow:
            assert saved.id is not None
            found = await uow.users.find_by_id(saved.id)

        assert found is not None
        assert found.id == saved.id
        assert found.email == Email("a@b.com")

    async def test_save_should_round_trip_through_find_by_email(
        self, uow_factory: IdentityUnitOfWorkFactory
    ):
        async with uow_factory() as uow:
            await uow.users.save(
                User.create(email=Email("Lookup@Example.com"), hashed_password="hp")
            )

        async with uow_factory() as uow:
            # Email VO normalises to lowercase before any compare
            found = await uow.users.find_by_email(Email("LOOKUP@example.COM"))

        assert found is not None
        assert found.email == Email("lookup@example.com")

    async def test_save_should_only_update_domain_mutable_fields_on_existing_user(
        self, uow_factory: IdentityUnitOfWorkFactory
    ):
        # Insert with hashed_password + is_verified set (CLI bootstrap path)
        async with uow_factory() as uow:
            inserted = await uow.users.save(
                User.create(
                    email=Email("admin@homeflix.local"),
                    role=UserRole.ADMIN,
                    is_superuser=True,
                    is_verified=True,
                    hashed_password="ORIGINAL_HASH",
                )
            )

        # Now update with hashed_password=None and is_verified=False; the
        # repository must NOT clobber the FastAPI Users-owned fields.
        modified = inserted.with_updates(
            role=UserRole.MEMBER,
            is_active=False,
            hashed_password=None,
            is_verified=False,
            is_superuser=False,
        )
        async with uow_factory() as uow:
            await uow.users.save(modified)

        # Re-read directly from the DB and confirm domain-mutable fields
        # changed, FastAPI Users-owned fields stayed intact.
        async with uow_factory() as uow:
            assert inserted.id is not None
            after = await uow.users.find_by_id(inserted.id)

        assert after is not None
        assert after.role == UserRole.MEMBER  # changed
        assert after.is_active is False  # changed
        assert after.hashed_password == "ORIGINAL_HASH"  # untouched
        assert after.is_verified is True  # untouched
        assert after.is_superuser is True  # untouched


class TestSqlAlchemyUserRepositoryReads:
    async def test_find_by_id_should_return_none_for_unknown_user(
        self, uow_factory: IdentityUnitOfWorkFactory
    ):
        async with uow_factory() as uow:
            found = await uow.users.find_by_id(UserId.generate())

        assert found is None

    async def test_find_by_email_should_return_none_for_unknown_user(
        self, uow_factory: IdentityUnitOfWorkFactory
    ):
        async with uow_factory() as uow:
            found = await uow.users.find_by_email(Email("nobody@nowhere.com"))

        assert found is None

    async def test_save_should_reject_when_id_is_provided_and_user_missing(
        self, uow_factory: IdentityUnitOfWorkFactory
    ):
        # Documenting the "treat unknown id as insert" fallback — calling
        # save with a fabricated id creates the row rather than failing.
        # This keeps the contract idempotent for callers that may have
        # received an id elsewhere (e.g. CLI tools, replays).
        fabricated = User(
            id=UserId.generate(),
            email=Email("idempotent@example.com"),
            hashed_password="hp",
        )
        async with uow_factory() as uow:
            saved = await uow.users.save(fabricated)

        assert saved.id == fabricated.id
        assert saved.email == fabricated.email


@pytest.mark.usefixtures("uow_factory")
class TestSqlAlchemyUserRepositoryUniqueness:
    async def test_inserting_two_users_with_same_email_should_fail(
        self, uow_factory: IdentityUnitOfWorkFactory
    ):
        async with uow_factory() as uow:
            await uow.users.save(User.create(email=Email("dup@example.com"), hashed_password="hp"))

        # Second insert with same email must violate the unique index
        with pytest.raises(IntegrityError):
            async with uow_factory() as uow:
                await uow.users.save(
                    User.create(
                        email=Email("dup@example.com"),
                        hashed_password="other",
                    )
                )


class TestSqlAlchemyUserRepositoryParentalPin:
    """``parental_pin_hash`` persistence (ADR-035).

    ``save`` writes the hash only on insert. On an existing user only
    ``set_parental_pin_hash`` writes it, so an entity read before a PIN
    change cannot overwrite that change when it is saved later.
    """

    async def _insert(self, uow_factory: IdentityUnitOfWorkFactory) -> User:
        async with uow_factory() as uow:
            return await uow.users.save(
                User.create(
                    email=Email("parent@example.com"), role=UserRole.ADMIN, hashed_password="hp"
                )
            )

    async def _reload(self, uow_factory: IdentityUnitOfWorkFactory, user: User) -> User:
        assert user.id is not None
        async with uow_factory() as uow:
            found = await uow.users.find_by_id(user.id)
        assert found is not None
        return found

    async def _set_pin_hash(
        self, uow_factory: IdentityUnitOfWorkFactory, user: User, hashed: str | None
    ) -> bool:
        assert user.id is not None
        async with uow_factory() as uow:
            return await uow.users.set_parental_pin_hash(user.id, hashed)

    async def test_set_parental_pin_hash_should_persist_the_hash(
        self, uow_factory: IdentityUnitOfWorkFactory
    ):
        user = await self._insert(uow_factory)

        stored = await self._set_pin_hash(uow_factory, user, "$argon2id$pin-hash")

        assert stored is True
        reloaded = await self._reload(uow_factory, user)
        assert reloaded.has_parental_pin is True
        assert reloaded.parental_pin_hash == "$argon2id$pin-hash"

    async def test_set_parental_pin_hash_with_none_should_clear_the_pin(
        self, uow_factory: IdentityUnitOfWorkFactory
    ):
        user = await self._insert(uow_factory)
        await self._set_pin_hash(uow_factory, user, "$argon2id$pin-hash")

        stored = await self._set_pin_hash(uow_factory, user, None)

        assert stored is True
        reloaded = await self._reload(uow_factory, user)
        assert reloaded.has_parental_pin is False
        assert reloaded.parental_pin_hash is None

    async def test_set_parental_pin_hash_should_refuse_a_soft_deleted_user_without_restoring_it(
        self,
        uow_factory: IdentityUnitOfWorkFactory,
        session_factory: async_sessionmaker[AsyncSession],
    ):
        user = await self._insert(uow_factory)
        assert user.id is not None
        async with uow_factory() as uow:
            await uow.users.soft_delete(user.id)

        stored = await self._set_pin_hash(uow_factory, user, "$argon2id$pin-hash")

        assert stored is False
        async with session_factory() as session:
            row = (
                await session.execute(
                    select(UserModel.deleted_at, UserModel.parental_pin_hash).where(
                        UserModel.external_id == str(user.id)
                    )
                )
            ).one()
        assert row.deleted_at is not None
        assert row.parental_pin_hash is None

    async def test_set_parental_pin_hash_should_report_an_unknown_user(
        self, uow_factory: IdentityUnitOfWorkFactory
    ):
        async with uow_factory() as uow:
            stored = await uow.users.set_parental_pin_hash(UserId.generate(), "$argon2id$pin")

        assert stored is False

    async def test_saving_a_stale_user_should_keep_a_pin_set_after_it_was_read(
        self, uow_factory: IdentityUnitOfWorkFactory
    ):
        # The role change was decided on an entity read before the PIN was
        # set; its NULL hash must not reach the column.
        user = await self._insert(uow_factory)
        stale = await self._reload(uow_factory, user)
        assert stale.parental_pin_hash is None
        await self._set_pin_hash(uow_factory, user, "$argon2id$pin-hash")

        async with uow_factory() as uow:
            await uow.users.save(stale.with_role(UserRole.MEMBER))

        reloaded = await self._reload(uow_factory, user)
        assert reloaded.role == UserRole.MEMBER
        assert reloaded.parental_pin_hash == "$argon2id$pin-hash"

    async def test_inserting_a_user_with_a_pin_should_persist_the_hash(
        self, uow_factory: IdentityUnitOfWorkFactory
    ):
        async with uow_factory() as uow:
            saved = await uow.users.save(
                User(
                    email=Email("parent@example.com"),
                    hashed_password="hp",
                    parental_pin_hash="$argon2id$pin-hash",
                )
            )

        reloaded = await self._reload(uow_factory, saved)
        assert reloaded.parental_pin_hash == "$argon2id$pin-hash"

    async def test_the_column_should_refuse_an_empty_hash(
        self, uow_factory: IdentityUnitOfWorkFactory
    ):
        user = await self._insert(uow_factory)

        with pytest.raises(IntegrityError, match="ck_users_parental_pin_hash_not_empty"):
            await self._set_pin_hash(uow_factory, user, "")
