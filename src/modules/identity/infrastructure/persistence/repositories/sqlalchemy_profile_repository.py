"""SQLAlchemy implementation of ProfileRepository."""

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select, update
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
from src.shared_kernel.value_objects.age_rating import AgeRating
from src.shared_kernel.value_objects.profile_id import ProfileId
from src.shared_kernel.value_objects.user_id import UserId


class SqlAlchemyProfileRepository(ProfileRepository):
    """Async SQLAlchemy repository for Profile aggregates.

    Bridges prefixed external IDs (domain) to UUIDs (database) for
    both ``Profile.id`` and ``Profile.user_id``. Soft-deletes on
    ``delete()``; transaction commit is the UoW's responsibility.

    On an existing profile the maturity limit has one writer,
    ``set_maturity_limit``: a single ``UPDATE`` whose ``WHERE`` carries the
    compare-and-set, reporting success by the row its ``RETURNING`` yields.
    ``rowcount`` cannot be used for that: with ``RETURNING`` on this stack
    (aiosqlite) it is ``-1`` whether a row matched or not.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, profile: Profile) -> Profile | None:
        """Persist a profile: insert a new one, update a live one, never restore a deleted one.

        Resolves ``profile.user_id`` to the user's internal UUID, looks the
        row up by ``external_id`` (deleted or not) and reloads via
        ``find_by_id`` so the returned entity carries the server-assigned
        timestamps.

        A missing row is inserted. An existing row is not written through the
        loaded model but by one ``UPDATE ... WHERE id = :id AND deleted_at IS
        NULL RETURNING id`` of the mutable columns whose value changes
        (``ProfileMapper.update_values``; nothing is written when none does).
        A soft-deleted profile is never restored: a rename, a library change
        or an avatar decided on a profile read before a concurrent delete —
        possibly followed by the removal of the PIN that protected its limit
        — gets ``None`` instead of bringing the profile back, whether the
        delete committed before the lookup, before the ``UPDATE`` or before
        the reload. An update leaves ``maturity_limit`` and ``is_kids`` as
        stored.

        The session is synchronised from the returned row, so a model of this
        profile already loaded in the session carries the new values.

        Args:
            profile: The profile to save.

        Returns:
            The saved profile, re-read so the caller sees timestamps; ``None``
            when the profile is soft-deleted, or is deleted before this write
            lands.

        Raises:
            ValueError: If the owning user does not exist.
        """
        profile = profile.with_updates(id=ProfileId.generate_if_absent(profile.id))
        if profile.id is None:
            raise RuntimeError("Profile id was not assigned before save")

        user_uuid = await self._resolve_user_uuid(profile.user_id)

        stmt = (
            select(ProfileModel)
            .where(ProfileModel.external_id == str(profile.id))
            .execution_options(populate_existing=True)
        )
        existing = (await self._session.execute(stmt)).scalar_one_or_none()

        if existing is None:
            model = ProfileMapper.to_model(profile, user_uuid=user_uuid)
            self._session.add(model)
            await self._session.flush()
            written = True
        else:
            written = not existing.is_deleted and await self._update_live(existing, profile)

        return await self.find_by_id(profile.id) if written else None

    async def _update_live(self, existing: ProfileModel, profile: Profile) -> bool:
        """Write the changed mutable columns while the row is live; ``False`` when it is not.

        ``rowcount`` cannot report the match: with ``RETURNING`` on this stack
        (aiosqlite) it is ``-1`` whether a row matched or not.
        """
        changes = {
            column: value
            for column, value in ProfileMapper.update_values(profile).items()
            if getattr(existing, column) != value
        }
        if not changes:
            return True
        stmt = (
            update(ProfileModel)
            .where(ProfileModel.id == existing.id, ProfileModel.deleted_at.is_(None))
            .values(**changes, updated_at=func.now())
            .returning(ProfileModel.id)
            .execution_options(synchronize_session="fetch")
        )
        return (await self._session.execute(stmt)).first() is not None

    async def set_maturity_limit(
        self,
        profile_id: ProfileId,
        *,
        expected: AgeRating | None,
        new: AgeRating | None,
    ) -> bool:
        """Compare-and-set the limit (and the derived ``is_kids``) in one ``UPDATE``.

        ``WHERE external_id = :id AND deleted_at IS NULL AND maturity_limit
        IS :expected``, plus, when ``new`` is a limit, ``EXISTS`` a PIN hash on
        the owning user, ``RETURNING`` the row id. SQLite admits one writer
        at a time, so a PIN removal racing this statement either committed
        before it (the ``EXISTS`` sees no PIN) or runs after this transaction
        commits and sees the limit. Under PostgreSQL READ COMMITTED the two
        statements would also need a row lock on the user.

        The session is synchronised from the returned row, so a model of this
        profile already loaded in the session carries the new limit.
        """
        p = ProfileModel
        conditions = [
            p.external_id == str(profile_id),
            p.deleted_at.is_(None),
            p.maturity_limit.is_not_distinct_from(None if expected is None else expected.value),
        ]
        if new is not None:
            conditions.append(
                select(UserModel.id)  # type: ignore[call-overload]  # fastapi-users typing
                .where(UserModel.id == p.user_id, UserModel.parental_pin_hash.is_not(None))
                .exists()
            )
        stmt = (
            update(p)
            .where(*conditions)
            .values(
                maturity_limit=None if new is None else new.value,
                is_kids=Profile.limit_reads_as_kids(new),
                updated_at=func.now(),
            )
            .returning(p.id)
            .execution_options(synchronize_session="fetch")
        )
        return (await self._session.execute(stmt)).first() is not None

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
