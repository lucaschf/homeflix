"""GetPreferencesUseCase."""

from src.modules.preferences.application.dtos.preferences_dtos import PreferencesOutput
from src.modules.preferences.infrastructure.persistence.repositories.preferences_repository import (
    PreferencesRepository,
)


class GetPreferencesUseCase:
    """Return the current user's playback preferences.

    If no row exists yet (first visit), returns the column defaults
    baked into ``PreferencesModel``.
    """

    def __init__(self, preferences_repository: PreferencesRepository) -> None:
        self._repo = preferences_repository

    async def execute(self) -> PreferencesOutput:
        """Fetch or default the user's playback preferences."""
        model = await self._repo.get()
        if model is None:
            # Return defaults — first visit, no row yet.
            return PreferencesOutput(
                audio_lang="pt-BR",
                subtitle_lang="pt-BR",
                subtitle_mode="foreignOnly",
                default_quality="best",
                speed=1.0,
            )
        return PreferencesOutput(
            audio_lang=model.audio_lang,
            subtitle_lang=model.subtitle_lang,
            subtitle_mode=model.subtitle_mode,
            default_quality=model.default_quality,
            speed=model.speed,
        )


__all__ = ["GetPreferencesUseCase"]
