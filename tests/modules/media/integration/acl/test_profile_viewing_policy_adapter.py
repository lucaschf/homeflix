"""Integration tests for the Media ProfileViewingPolicyAdapter."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

# Importing the identity models ensures Base.metadata.create_all
# (called by the integration conftest) discovers ``users`` /
# ``profiles`` / ``access_tokens``.
import src.modules.identity.infrastructure.persistence.models  # noqa: F401
from src.modules.identity.domain.entities.profile import Profile
from src.modules.identity.domain.entities.user import User
from src.modules.identity.domain.value_objects.email import Email
from src.modules.identity.domain.value_objects.profile_name import ProfileName
from src.modules.identity.infrastructure.persistence.sqlalchemy_unit_of_work import (
    SqlAlchemyIdentityUnitOfWorkFactory,
)
from src.modules.media.infrastructure.acl import ProfileViewingPolicyAdapter
from src.shared_kernel.content_policy import ViewingPolicy
from src.shared_kernel.value_objects.profile_id import ProfileId


async def _seed_profile(
    factory: SqlAlchemyIdentityUnitOfWorkFactory,
    *,
    email: str,
    profile_name: str,
    allowed_library_ids: list[str],
) -> Profile:
    """Create + persist a user and a single profile, returning the profile."""
    async with factory() as uow:
        user = await uow.users.save(User.create(email=Email(email), hashed_password="hp"))
        assert user.id is not None
        return await uow.profiles.save(
            Profile.create(
                user_id=user.id,
                name=ProfileName(profile_name),
                allowed_library_ids=allowed_library_ids,
            )
        )


def _make_adapter(
    session_factory: async_sessionmaker[AsyncSession],
) -> ProfileViewingPolicyAdapter:
    return ProfileViewingPolicyAdapter(SqlAlchemyIdentityUnitOfWorkFactory(session_factory))


@pytest.mark.integration
class TestProfileViewingPolicyAdapter:
    async def test_should_return_library_policy_for_known_profile(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        factory = SqlAlchemyIdentityUnitOfWorkFactory(session_factory)
        granted = ["lib_movies123456", "lib_series123456"]
        profile = await _seed_profile(
            factory,
            email="lucas@homeflix.local",
            profile_name="Lucas",
            allowed_library_ids=granted,
        )

        adapter = _make_adapter(session_factory)

        assert profile.id is not None
        policy = await adapter.find_for_profile(profile.id)
        assert policy == ViewingPolicy.unrestricted(granted)
        # ``Profile`` has no maturity limit yet, so the age axis is open.
        assert policy.maturity_limit is None

    async def test_should_return_deny_all_policy_for_default_deny_profile(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        factory = SqlAlchemyIdentityUnitOfWorkFactory(session_factory)
        profile = await _seed_profile(
            factory,
            email="anon@homeflix.local",
            profile_name="Anon",
            allowed_library_ids=[],
        )

        adapter = _make_adapter(session_factory)

        assert profile.id is not None
        assert (await adapter.find_for_profile(profile.id)).denies_everything is True

    async def test_should_return_deny_all_policy_for_unknown_profile_id(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        # Deny-all is the safer default than raising — the adapter
        # is the only thing standing between an absent profile and
        # the catalog reads downstream.
        adapter = _make_adapter(session_factory)

        policy = await adapter.find_for_profile(ProfileId("prf_doesnotexist"))
        assert policy.denies_everything is True

    async def test_should_isolate_acls_across_profiles(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        factory = SqlAlchemyIdentityUnitOfWorkFactory(session_factory)
        a = await _seed_profile(
            factory,
            email="a@homeflix.local",
            profile_name="A",
            allowed_library_ids=["lib_aaaaaaaaaaaa"],
        )
        b = await _seed_profile(
            factory,
            email="b@homeflix.local",
            profile_name="B",
            allowed_library_ids=["lib_bbbbbbbbbb01", "lib_bbbbbbbbbb02"],
        )

        adapter = _make_adapter(session_factory)

        assert a.id is not None
        assert b.id is not None
        assert await adapter.find_for_profile(a.id) == ViewingPolicy.unrestricted(
            ["lib_aaaaaaaaaaaa"]
        )
        assert await adapter.find_for_profile(b.id) == ViewingPolicy.unrestricted(
            ["lib_bbbbbbbbbb01", "lib_bbbbbbbbbb02"]
        )
