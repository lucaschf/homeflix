"""Integration tests for SqlAlchemyAccessTokenRepository."""

import secrets
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.identity.application.unit_of_work import IdentityUnitOfWorkFactory
from src.modules.identity.domain.entities.profile import Profile
from src.modules.identity.domain.entities.user import User
from src.modules.identity.domain.value_objects.email import Email
from src.modules.identity.domain.value_objects.profile_id import ProfileId
from src.modules.identity.domain.value_objects.profile_name import ProfileName
from src.modules.identity.infrastructure.persistence.models.access_token_model import (
    AccessTokenModel,
)
from src.modules.identity.infrastructure.persistence.models.profile_model import (
    ProfileModel,
)
from src.modules.identity.infrastructure.persistence.models.user_model import UserModel


def _new_token() -> str:
    """Mimic FastAPI Users' default token generation (43 base64url chars)."""
    return secrets.token_urlsafe(32)


async def _seed_user(
    uow_factory: IdentityUnitOfWorkFactory,
    email: str = "owner@example.com",
) -> User:
    async with uow_factory() as uow:
        return await uow.users.save(User.create(email=Email(email), hashed_password="hp"))


async def _user_uuid(db_session: AsyncSession, external_id: str) -> uuid.UUID:
    result = await db_session.execute(
        select(UserModel.id).where(UserModel.external_id == external_id)
    )
    return result.scalar_one()


async def _profile_uuid(db_session: AsyncSession, external_id: str) -> uuid.UUID:
    result = await db_session.execute(
        select(ProfileModel.id).where(ProfileModel.external_id == external_id)
    )
    return result.scalar_one()


async def _insert_access_token(
    db_session: AsyncSession,
    *,
    token: str,
    user_uuid: uuid.UUID,
    current_profile_uuid: uuid.UUID | None = None,
    created_at: datetime | None = None,
) -> None:
    row = AccessTokenModel(
        token=token,
        user_id=user_uuid,
        current_profile_id=current_profile_uuid,
    )
    if created_at is not None:
        row.created_at = created_at
    db_session.add(row)
    await db_session.commit()


class TestGetByToken:
    async def test_should_return_snapshot_with_prefixed_user_id(
        self,
        uow_factory: IdentityUnitOfWorkFactory,
        db_session: AsyncSession,
    ):
        owner = await _seed_user(uow_factory)
        assert owner.id is not None
        owner_uuid = await _user_uuid(db_session, owner.id.value)
        token = _new_token()
        await _insert_access_token(db_session, token=token, user_uuid=owner_uuid)

        async with uow_factory() as uow:
            snap = await uow.access_tokens.get_by_token(token)

        assert snap is not None
        assert snap.token == token
        assert snap.user_id == owner.id
        assert snap.current_profile_id is None
        assert snap.created_at.tzinfo is not None

    async def test_should_resolve_current_profile_to_prefixed_id(
        self,
        uow_factory: IdentityUnitOfWorkFactory,
        db_session: AsyncSession,
    ):
        owner = await _seed_user(uow_factory)
        assert owner.id is not None

        async with uow_factory() as uow:
            profile = await uow.profiles.save(
                Profile.create(user_id=owner.id, name=ProfileName("Lucas"))
            )

        owner_uuid = await _user_uuid(db_session, owner.id.value)
        assert profile.id is not None
        profile_uuid = await _profile_uuid(db_session, profile.id.value)
        token = _new_token()
        await _insert_access_token(
            db_session,
            token=token,
            user_uuid=owner_uuid,
            current_profile_uuid=profile_uuid,
        )

        async with uow_factory() as uow:
            snap = await uow.access_tokens.get_by_token(token)

        assert snap is not None
        assert snap.current_profile_id == profile.id

    async def test_should_return_none_for_unknown_token(
        self, uow_factory: IdentityUnitOfWorkFactory
    ):
        async with uow_factory() as uow:
            snap = await uow.access_tokens.get_by_token("nonexistent")

        assert snap is None


class TestUpdateCurrentProfile:
    async def test_should_set_active_profile_on_existing_session(
        self,
        uow_factory: IdentityUnitOfWorkFactory,
        db_session: AsyncSession,
    ):
        owner = await _seed_user(uow_factory)
        assert owner.id is not None

        async with uow_factory() as uow:
            profile = await uow.profiles.save(
                Profile.create(user_id=owner.id, name=ProfileName("Lucas"))
            )

        owner_uuid = await _user_uuid(db_session, owner.id.value)
        token = _new_token()
        await _insert_access_token(db_session, token=token, user_uuid=owner_uuid)

        assert profile.id is not None
        async with uow_factory() as uow:
            ok = await uow.access_tokens.update_current_profile(token, profile.id)

        assert ok is True
        async with uow_factory() as uow:
            snap = await uow.access_tokens.get_by_token(token)
        assert snap is not None
        assert snap.current_profile_id == profile.id

    async def test_should_clear_active_profile_when_passing_none(
        self,
        uow_factory: IdentityUnitOfWorkFactory,
        db_session: AsyncSession,
    ):
        owner = await _seed_user(uow_factory)
        assert owner.id is not None

        async with uow_factory() as uow:
            profile = await uow.profiles.save(
                Profile.create(user_id=owner.id, name=ProfileName("Lucas"))
            )

        owner_uuid = await _user_uuid(db_session, owner.id.value)
        assert profile.id is not None
        profile_uuid = await _profile_uuid(db_session, profile.id.value)
        token = _new_token()
        await _insert_access_token(
            db_session,
            token=token,
            user_uuid=owner_uuid,
            current_profile_uuid=profile_uuid,
        )

        async with uow_factory() as uow:
            ok = await uow.access_tokens.update_current_profile(token, None)

        assert ok is True
        async with uow_factory() as uow:
            snap = await uow.access_tokens.get_by_token(token)
        assert snap is not None
        assert snap.current_profile_id is None

    async def test_should_return_false_when_token_does_not_exist(
        self, uow_factory: IdentityUnitOfWorkFactory
    ):
        async with uow_factory() as uow:
            ok = await uow.access_tokens.update_current_profile("ghost-token", profile_id=None)

        assert ok is False

    async def test_should_raise_when_profile_does_not_exist(
        self,
        uow_factory: IdentityUnitOfWorkFactory,
        db_session: AsyncSession,
    ):
        owner = await _seed_user(uow_factory)
        assert owner.id is not None
        owner_uuid = await _user_uuid(db_session, owner.id.value)
        token = _new_token()
        await _insert_access_token(db_session, token=token, user_uuid=owner_uuid)

        with pytest.raises(ValueError, match="does not exist"):
            async with uow_factory() as uow:
                await uow.access_tokens.update_current_profile(token, ProfileId.generate())


class TestDeleteOlderThan:
    async def test_should_remove_sessions_older_than_cutoff(
        self,
        uow_factory: IdentityUnitOfWorkFactory,
        db_session: AsyncSession,
    ):
        owner = await _seed_user(uow_factory)
        assert owner.id is not None
        owner_uuid = await _user_uuid(db_session, owner.id.value)

        now = datetime.now(UTC)
        old_token = _new_token()
        recent_token = _new_token()
        await _insert_access_token(
            db_session,
            token=old_token,
            user_uuid=owner_uuid,
            created_at=now - timedelta(days=100),
        )
        await _insert_access_token(
            db_session,
            token=recent_token,
            user_uuid=owner_uuid,
            created_at=now - timedelta(days=10),
        )

        cutoff = now - timedelta(days=90)
        async with uow_factory() as uow:
            removed = await uow.access_tokens.delete_older_than(cutoff)

        assert removed == 1

        async with uow_factory() as uow:
            assert await uow.access_tokens.get_by_token(old_token) is None
            assert await uow.access_tokens.get_by_token(recent_token) is not None

    async def test_should_return_zero_when_no_sessions_match(
        self, uow_factory: IdentityUnitOfWorkFactory
    ):
        async with uow_factory() as uow:
            removed = await uow.access_tokens.delete_older_than(
                datetime.now(UTC) - timedelta(days=365)
            )

        assert removed == 0
