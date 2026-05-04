"""Integration tests for the Media ProfileLibraryAccessAdapter."""

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
from src.modules.media.infrastructure.acl import ProfileLibraryAccessAdapter


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
) -> ProfileLibraryAccessAdapter:
    return ProfileLibraryAccessAdapter(SqlAlchemyIdentityUnitOfWorkFactory(session_factory))


@pytest.mark.integration
class TestProfileLibraryAccessAdapter:
    async def test_should_return_allowed_library_ids_for_known_profile(
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
        assert await adapter.find_for_profile(profile.id.value) == granted

    async def test_should_return_empty_list_for_default_deny_profile(
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
        assert await adapter.find_for_profile(profile.id.value) == []

    async def test_should_return_empty_list_for_unknown_profile_id(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        # Deny-all is the safer default than raising — the adapter
        # is the only thing standing between an absent profile and
        # the catalog reads downstream.
        adapter = _make_adapter(session_factory)

        assert await adapter.find_for_profile("prf_doesnotexist") == []

    async def test_should_isolate_acls_across_profiles(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        factory = SqlAlchemyIdentityUnitOfWorkFactory(session_factory)
        a = await _seed_profile(
            factory,
            email="a@homeflix.local",
            profile_name="A",
            allowed_library_ids=["lib_a"],
        )
        b = await _seed_profile(
            factory,
            email="b@homeflix.local",
            profile_name="B",
            allowed_library_ids=["lib_b1", "lib_b2"],
        )

        adapter = _make_adapter(session_factory)

        assert a.id is not None
        assert b.id is not None
        assert await adapter.find_for_profile(a.id.value) == ["lib_a"]
        assert await adapter.find_for_profile(b.id.value) == ["lib_b1", "lib_b2"]
