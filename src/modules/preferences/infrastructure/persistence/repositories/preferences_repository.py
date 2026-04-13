"""SQLAlchemy repository for user preferences (singleton-per-user)."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.preferences.infrastructure.persistence.models.preferences_model import (
    PreferencesModel,
)

DEFAULT_USER_KEY = "default"


class PreferencesRepository:
    """Read/upsert the preferences row for a given user key.

    Until auth lands, every call uses ``DEFAULT_USER_KEY``.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, user_key: str = DEFAULT_USER_KEY) -> PreferencesModel | None:
        """Return the preferences row or ``None`` if none exists yet."""
        stmt = select(PreferencesModel).where(
            PreferencesModel.user_key == user_key,
            PreferencesModel.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def upsert(
        self,
        *,
        user_key: str = DEFAULT_USER_KEY,
        audio_lang: str | None = None,
        subtitle_lang: str | None = None,
        subtitle_mode: str | None = None,
        default_quality: str | None = None,
        speed: float | None = None,
    ) -> PreferencesModel:
        """Create or update the preferences row.

        Only non-``None`` fields are touched — callers can send a
        partial update and the rest keeps its current value (or the
        column default for a brand-new row).
        """
        model = await self.get(user_key)

        if model is None:
            model = PreferencesModel(
                external_id=f"prf_{user_key}",
                user_key=user_key,
            )
            self._session.add(model)

        if audio_lang is not None:
            model.audio_lang = audio_lang
        if subtitle_lang is not None:
            model.subtitle_lang = subtitle_lang
        if subtitle_mode is not None:
            model.subtitle_mode = subtitle_mode
        if default_quality is not None:
            model.default_quality = default_quality
        if speed is not None:
            model.speed = speed

        await self._session.flush()
        await self._session.commit()

        # Re-read so we return server-generated timestamps.
        refreshed = await self.get(user_key)
        assert refreshed is not None
        return refreshed


__all__ = ["PreferencesRepository"]
