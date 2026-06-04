"""Integration tests for SqlAlchemyProfileRepository."""

import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.identity.application.unit_of_work import IdentityUnitOfWorkFactory
from src.modules.identity.domain.entities.profile import Profile
from src.modules.identity.domain.entities.user import User
from src.modules.identity.domain.value_objects.email import Email
from src.modules.identity.domain.value_objects.profile_name import ProfileName
from src.modules.identity.infrastructure.persistence.models.profile_model import (
    ProfileModel,
)
from src.shared_kernel.value_objects.library_id import LibraryId
from src.shared_kernel.value_objects.profile_id import ProfileId
from src.shared_kernel.value_objects.user_id import UserId


async def _seed_user(
    uow_factory: IdentityUnitOfWorkFactory, email: str = "owner@example.com"
) -> User:
    """Create and return a persisted user (helper for profile tests)."""
    async with uow_factory() as uow:
        return await uow.users.save(User.create(email=Email(email), hashed_password="hp"))


class TestSqlAlchemyProfileRepositorySave:
    async def test_should_persist_a_new_profile_and_assign_external_id(
        self, uow_factory: IdentityUnitOfWorkFactory
    ):
        owner = await _seed_user(uow_factory)
        assert owner.id is not None

        async with uow_factory() as uow:
            saved = await uow.profiles.save(
                Profile.create(user_id=owner.id, name=ProfileName("Lucas")),
            )

        assert saved.id is not None
        assert saved.id.prefix == "prf"
        assert saved.user_id == owner.id
        assert saved.name == ProfileName("Lucas")
        assert saved.is_kids is False

    async def test_should_round_trip_through_find_by_id(
        self, uow_factory: IdentityUnitOfWorkFactory
    ):
        owner = await _seed_user(uow_factory)
        assert owner.id is not None

        async with uow_factory() as uow:
            saved = await uow.profiles.save(
                Profile.create(
                    user_id=owner.id,
                    name=ProfileName("Kids"),
                    is_kids=True,
                    avatar_url="https://example.com/k.png",
                )
            )

        async with uow_factory() as uow:
            assert saved.id is not None
            found = await uow.profiles.find_by_id(saved.id)

        assert found is not None
        assert found.id == saved.id
        assert found.user_id == owner.id
        assert found.is_kids is True
        assert found.avatar_url == "https://example.com/k.png"

    async def test_save_should_update_existing_profile(
        self, uow_factory: IdentityUnitOfWorkFactory
    ):
        owner = await _seed_user(uow_factory)
        assert owner.id is not None

        async with uow_factory() as uow:
            original = await uow.profiles.save(
                Profile.create(user_id=owner.id, name=ProfileName("Old"))
            )

        renamed = original.with_name(ProfileName("New"))

        async with uow_factory() as uow:
            await uow.profiles.save(renamed)

        async with uow_factory() as uow:
            assert original.id is not None
            after = await uow.profiles.find_by_id(original.id)

        assert after is not None
        assert after.name == ProfileName("New")

    async def test_save_should_reject_when_owning_user_does_not_exist(
        self, uow_factory: IdentityUnitOfWorkFactory
    ):
        ghost_user_id = UserId.generate()

        with pytest.raises(ValueError, match="does not exist"):
            async with uow_factory() as uow:
                await uow.profiles.save(
                    Profile.create(user_id=ghost_user_id, name=ProfileName("Ghost"))
                )

    async def test_should_round_trip_allowed_library_ids(
        self, uow_factory: IdentityUnitOfWorkFactory
    ):
        owner = await _seed_user(uow_factory)
        assert owner.id is not None

        granted = ["lib_movies123456", "lib_series123456"]
        async with uow_factory() as uow:
            saved = await uow.profiles.save(
                Profile.create(
                    user_id=owner.id,
                    name=ProfileName("Lucas"),
                    allowed_library_ids=granted,
                )
            )

        assert saved.id is not None
        async with uow_factory() as uow:
            found = await uow.profiles.find_by_id(saved.id)

        assert found is not None
        assert found.allowed_library_ids == [LibraryId(library_id) for library_id in granted]

    async def test_should_default_allowed_library_ids_to_empty_when_unset(
        self, uow_factory: IdentityUnitOfWorkFactory
    ):
        # Default-deny: a freshly persisted profile with no explicit
        # ACL must round-trip as an empty list, not as null or any
        # legacy "see everything" sentinel.
        owner = await _seed_user(uow_factory)
        assert owner.id is not None

        async with uow_factory() as uow:
            saved = await uow.profiles.save(
                Profile.create(user_id=owner.id, name=ProfileName("Anon"))
            )

        async with uow_factory() as uow:
            assert saved.id is not None
            found = await uow.profiles.find_by_id(saved.id)

        assert found is not None
        assert found.allowed_library_ids == []

    async def test_should_coerce_corrupted_allowed_library_ids_to_empty(
        self,
        uow_factory: IdentityUnitOfWorkFactory,
        db_session: AsyncSession,
    ) -> None:
        # A corrupted JSON payload (e.g. an old deploy that wrote a
        # scalar) must never be interpreted as "grant something" — the
        # mapper coerces to an empty list and logs a warning so the
        # corruption is observable in dashboards rather than silently
        # turning a deny-all ACL into anything else.
        owner = await _seed_user(uow_factory)
        assert owner.id is not None

        async with uow_factory() as uow:
            saved = await uow.profiles.save(
                Profile.create(
                    user_id=owner.id,
                    name=ProfileName("L"),
                    allowed_library_ids=["lib_originaltttt"],
                )
            )

        # Force a corrupted payload directly into the row (simulates
        # an older release writing a non-list value).
        assert saved.id is not None
        await db_session.execute(
            update(ProfileModel)
            .where(ProfileModel.external_id == saved.id.value)
            .values(allowed_library_ids='{"not": "a list"}')
        )
        await db_session.commit()

        async with uow_factory() as uow:
            after = await uow.profiles.find_by_id(saved.id)

        assert after is not None
        assert after.allowed_library_ids == []

    async def test_should_drop_invalid_entries_from_allowed_library_ids(
        self,
        uow_factory: IdentityUnitOfWorkFactory,
        db_session: AsyncSession,
    ) -> None:
        # Default-deny per entry (ADR-018): a malformed id inside an
        # otherwise valid list is dropped with a WARNING — it must
        # neither grant access nor make the whole profile unreadable.
        owner = await _seed_user(uow_factory)
        assert owner.id is not None

        async with uow_factory() as uow:
            saved = await uow.profiles.save(
                Profile.create(
                    user_id=owner.id,
                    name=ProfileName("L"),
                    allowed_library_ids=["lib_originaltttt"],
                )
            )

        assert saved.id is not None
        await db_session.execute(
            update(ProfileModel)
            .where(ProfileModel.external_id == saved.id.value)
            .values(allowed_library_ids='["lib_originaltttt", "not-a-lib-id", "mov_wrongprefix1"]')
        )
        await db_session.commit()

        async with uow_factory() as uow:
            after = await uow.profiles.find_by_id(saved.id)

        assert after is not None
        assert after.allowed_library_ids == [LibraryId("lib_originaltttt")]

    async def test_save_should_replace_allowed_library_ids_on_update(
        self, uow_factory: IdentityUnitOfWorkFactory
    ):
        # The aggregate's with_allowed_library_ids replaces the list
        # entirely; persistence must mirror that semantics so a
        # subsequent revoke (passing []) is durable.
        owner = await _seed_user(uow_factory)
        assert owner.id is not None

        async with uow_factory() as uow:
            original = await uow.profiles.save(
                Profile.create(
                    user_id=owner.id,
                    name=ProfileName("L"),
                    allowed_library_ids=["lib_aaaaaaaaaaaa", "lib_bbbbbbbbbbbb"],
                )
            )

        revoked = original.with_allowed_library_ids([])

        async with uow_factory() as uow:
            await uow.profiles.save(revoked)

        async with uow_factory() as uow:
            assert original.id is not None
            after = await uow.profiles.find_by_id(original.id)

        assert after is not None
        assert after.allowed_library_ids == []


class TestSqlAlchemyProfileRepositoryReads:
    async def test_find_by_id_should_return_none_for_unknown_profile(
        self, uow_factory: IdentityUnitOfWorkFactory
    ):
        async with uow_factory() as uow:
            found = await uow.profiles.find_by_id(ProfileId.generate())

        assert found is None

    async def test_find_by_user_should_isolate_by_owner(
        self, uow_factory: IdentityUnitOfWorkFactory
    ):
        alice = await _seed_user(uow_factory, email="alice@example.com")
        bob = await _seed_user(uow_factory, email="bob@example.com")
        assert alice.id is not None and bob.id is not None

        async with uow_factory() as uow:
            await uow.profiles.save(Profile.create(user_id=alice.id, name=ProfileName("Alice")))
            await uow.profiles.save(
                Profile.create(user_id=alice.id, name=ProfileName("Alice Kids"))
            )
            await uow.profiles.save(Profile.create(user_id=bob.id, name=ProfileName("Bob")))

        async with uow_factory() as uow:
            alice_profiles = await uow.profiles.find_by_user(alice.id)
            bob_profiles = await uow.profiles.find_by_user(bob.id)

        assert len(alice_profiles) == 2
        assert len(bob_profiles) == 1
        assert {p.name.value for p in alice_profiles} == {"Alice", "Alice Kids"}
        assert {p.name.value for p in bob_profiles} == {"Bob"}

    async def test_find_by_user_should_order_by_name(self, uow_factory: IdentityUnitOfWorkFactory):
        owner = await _seed_user(uow_factory)
        assert owner.id is not None

        async with uow_factory() as uow:
            for n in ("Charlie", "Alice", "Bob"):
                await uow.profiles.save(Profile.create(user_id=owner.id, name=ProfileName(n)))

        async with uow_factory() as uow:
            profiles = await uow.profiles.find_by_user(owner.id)

        assert [p.name.value for p in profiles] == ["Alice", "Bob", "Charlie"]

    async def test_count_for_user_should_return_active_profile_count(
        self, uow_factory: IdentityUnitOfWorkFactory
    ):
        owner = await _seed_user(uow_factory)
        assert owner.id is not None

        async with uow_factory() as uow:
            for n in ("A", "B", "C"):
                await uow.profiles.save(Profile.create(user_id=owner.id, name=ProfileName(n)))

        async with uow_factory() as uow:
            count = await uow.profiles.count_for_user(owner.id)

        assert count == 3


class TestSqlAlchemyProfileRepositoryDelete:
    async def test_delete_should_soft_delete_an_existing_profile(
        self, uow_factory: IdentityUnitOfWorkFactory
    ):
        owner = await _seed_user(uow_factory)
        assert owner.id is not None

        async with uow_factory() as uow:
            saved = await uow.profiles.save(
                Profile.create(user_id=owner.id, name=ProfileName("Doomed"))
            )

        async with uow_factory() as uow:
            assert saved.id is not None
            ok = await uow.profiles.delete(saved.id)

        assert ok is True

        # find_by_id excludes soft-deleted rows
        async with uow_factory() as uow:
            assert saved.id is not None
            assert await uow.profiles.find_by_id(saved.id) is None

        # count_for_user does NOT include soft-deleted rows
        async with uow_factory() as uow:
            assert await uow.profiles.count_for_user(owner.id) == 0

    async def test_delete_should_return_false_for_unknown_profile(
        self, uow_factory: IdentityUnitOfWorkFactory
    ):
        async with uow_factory() as uow:
            ok = await uow.profiles.delete(ProfileId.generate())

        assert ok is False
