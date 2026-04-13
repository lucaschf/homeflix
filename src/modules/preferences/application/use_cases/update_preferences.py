"""UpdatePreferencesUseCase."""

from src.modules.preferences.application.dtos.preferences_dtos import (
    PreferencesOutput,
    UpdatePreferencesInput,
)
from src.modules.preferences.infrastructure.persistence.repositories.preferences_repository import (
    PreferencesRepository,
)


class UpdatePreferencesUseCase:
    """Partially update (or create) the user's playback preferences."""

    def __init__(self, preferences_repository: PreferencesRepository) -> None:
        self._repo = preferences_repository

    async def execute(self, input_dto: UpdatePreferencesInput) -> PreferencesOutput:
        """Upsert the user's playback preferences."""
        model = await self._repo.upsert(
            audio_lang=input_dto.audio_lang,
            subtitle_lang=input_dto.subtitle_lang,
            subtitle_mode=input_dto.subtitle_mode,
            default_quality=input_dto.default_quality,
            speed=input_dto.speed,
        )
        return PreferencesOutput(
            audio_lang=model.audio_lang,
            subtitle_lang=model.subtitle_lang,
            subtitle_mode=model.subtitle_mode,
            default_quality=model.default_quality,
            speed=model.speed,
        )


__all__ = ["UpdatePreferencesUseCase"]
