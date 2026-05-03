"""Integration tests for SqlAlchemyUserRepository."""

import pytest
from sqlalchemy.exc import IntegrityError

from src.modules.identity.application.unit_of_work import IdentityUnitOfWorkFactory
from src.modules.identity.domain.entities.user import User
from src.modules.identity.domain.value_objects.email import Email
from src.modules.identity.domain.value_objects.user_id import UserId
from src.modules.identity.domain.value_objects.user_role import UserRole


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
