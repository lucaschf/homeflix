"""SQLAlchemy repository implementing ``PreferencesRepository``."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.preferences.domain.entities import PlaybackPreferences
from src.modules.preferences.domain.repositories import PreferencesRepository
from src.modules.preferences.infrastructure.persistence.mappers import PreferencesMapper
from src.modules.preferences.infrastructure.persistence.models.preferences_model import (
    PreferencesModel,
)
from src.shared_kernel.value_objects.profile_id import ProfileId


class SQLAlchemyPreferencesRepository(PreferencesRepository):
    """Persist preferences via SQLAlchemy.

    Transaction boundary is owned by the surrounding Unit of Work —
    this class never calls ``commit()`` or ``rollback()``.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_by_profile_id(self, profile_id: ProfileId) -> PlaybackPreferences | None:
        """Map the persisted row (if any) back into a domain entity."""
        model = await self._fetch_model(profile_id)
        return PreferencesMapper.to_entity(model) if model else None

    async def save(self, preferences: PlaybackPreferences) -> PlaybackPreferences:
        """Upsert the row; flush but leave the commit to the Unit of Work."""
        existing = await self._fetch_model(preferences.profile_id)
        if existing is None:
            model = PreferencesMapper.new_model(preferences)
            self._session.add(model)
        else:
            model = PreferencesMapper.update_model(existing, preferences)

        # Flush so server-generated timestamps/defaults land on the
        # in-memory instance without committing — that's the UoW's job.
        await self._session.flush()
        await self._session.refresh(model)
        return PreferencesMapper.to_entity(model)

    async def _fetch_model(self, profile_id: ProfileId) -> PreferencesModel | None:
        stmt = select(PreferencesModel).where(
            PreferencesModel.profile_id == str(profile_id),
            PreferencesModel.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()


__all__ = ["SQLAlchemyPreferencesRepository"]
