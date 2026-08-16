"""SQLAlchemy implementation of ProfileRepository."""

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.identity.domain.entities.profile import Profile
from src.modules.identity.domain.repositories.profile_repository import (
    ProfileRepository,
)
from src.modules.identity.infrastructure.persistence.mappers.profile_mapper import (
    ProfileMapper,
)
from src.modules.identity.infrastructure.persistence.models.profile_model import (
    ProfileModel,
)
from src.modules.identity.infrastructure.persistence.models.user_model import UserModel
from src.shared_kernel.value_objects.profile_id import ProfileId
from src.shared_kernel.value_objects.user_id import UserId


class SqlAlchemyProfileRepository(ProfileRepository):
    """Async SQLAlchemy repository for Profile aggregates.

    Bridges prefixed external IDs (domain) to UUIDs (database) for
    both ``Profile.id`` and ``Profile.user_id``. Soft-deletes on
    ``delete()``; transaction commit is the UoW's responsibility.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, profile: Profile) -> Profile:
        """Persist a profile (insert when missing, update when found).

        Resolves ``profile.user_id`` to the user's internal UUID
        before passing the entity to the mapper. Follows the same
        shape as ``SqlAlchemyLibraryRepository.save``: always look the
        row up by ``external_id`` first; restore a soft-deleted row
        before applying updates; reload via ``find_by_id`` so the
        returned entity carries the server-assigned timestamps.

        Args:
            profile: The profile to save.

        Returns:
            The saved profile, re-read so the caller sees timestamps.

        Raises:
            ValueError: If the owning user does not exist.
        """
        profile = profile.with_updates(id=ProfileId.generate_if_absent(profile.id))

        user_uuid = await self._resolve_user_uuid(profile.user_id)

        stmt = select(ProfileModel).where(ProfileModel.external_id == str(profile.id))
        existing = (await self._session.execute(stmt)).scalar_one_or_none()

        if existing is not None and existing.is_deleted:
            existing.restore()

        if existing is not None:
            ProfileMapper.update_model(existing, profile)
            await self._session.flush()
        else:
            model = ProfileMapper.to_model(profile, user_uuid=user_uuid)
            self._session.add(model)
            await self._session.flush()

        if profile.id is None:
            raise RuntimeError("Profile id was not assigned before save")
        saved = await self.find_by_id(profile.id)
        if saved is None:
            raise RuntimeError(
                f"Profile {profile.id} disappeared between flush and reload",
            )
        return saved

    async def find_by_id(self, profile_id: ProfileId) -> Profile | None:
        """Look up a non-deleted profile by external ID, returning a domain entity."""
        stmt = (
            select(ProfileModel, UserModel.external_id)
            .join(UserModel, ProfileModel.user_id == UserModel.id)
            .where(
                ProfileModel.external_id == str(profile_id),
                ProfileModel.deleted_at.is_(None),
            )
        )
        result = await self._session.execute(stmt)
        row = result.first()
        if row is None:
            return None
        model, user_external_id = row
        return ProfileMapper.to_entity(model, user_external_id=user_external_id)

    async def find_by_user(self, user_id: UserId) -> Sequence[Profile]:
        """List all non-deleted profiles owned by the user, ordered by name."""
        stmt = (
            select(ProfileModel, UserModel.external_id)
            .join(UserModel, ProfileModel.user_id == UserModel.id)
            .where(
                UserModel.external_id == str(user_id),
                ProfileModel.deleted_at.is_(None),
            )
            .order_by(ProfileModel.name)
        )
        result = await self._session.execute(stmt)
        rows = result.all()
        return [
            ProfileMapper.to_entity(model, user_external_id=user_external_id)
            for model, user_external_id in rows
        ]

    async def count_for_user(self, user_id: UserId) -> int:
        """Count non-deleted profiles owned by the user."""
        stmt = (
            select(func.count(ProfileModel.id))
            .join(UserModel, ProfileModel.user_id == UserModel.id)
            .where(
                UserModel.external_id == str(user_id),
                ProfileModel.deleted_at.is_(None),
            )
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def delete(self, profile_id: ProfileId) -> bool:
        """Soft-delete a profile by external ID."""
        stmt = select(ProfileModel).where(
            ProfileModel.external_id == str(profile_id),
            ProfileModel.deleted_at.is_(None),
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        if model is None:
            return False
        model.soft_delete()
        await self._session.flush()
        return True

    async def _resolve_user_uuid(self, user_id: UserId) -> uuid.UUID:
        """Translate prefixed UserId → internal UUID via SELECT."""
        stmt = select(UserModel.id).where(UserModel.external_id == str(user_id))  # type: ignore[call-overload]  # fastapi-users typing
        result = await self._session.execute(stmt)
        user_uuid = result.scalar_one_or_none()
        if user_uuid is None:
            raise ValueError(f"User {user_id} does not exist")
        return user_uuid  # type: ignore[no-any-return]  # fastapi-users typing


__all__ = ["SqlAlchemyProfileRepository"]
