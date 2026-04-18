"""UpdatePreferencesUseCase."""

from src.modules.preferences.application.dtos.preferences_dtos import (
    PreferencesOutput,
    UpdatePreferencesInput,
)
from src.modules.preferences.application.unit_of_work import PreferencesUnitOfWorkFactory
from src.modules.preferences.domain.entities import DEFAULT_USER_KEY, PlaybackPreferences


class UpdatePreferencesUseCase:
    """Partially update (or create) the user's playback preferences."""

    def __init__(self, uow_factory: PreferencesUnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def execute(self, input_dto: UpdatePreferencesInput) -> PreferencesOutput:
        """Upsert the user's playback preferences.

        Loads the current record (or builds defaults on first save),
        applies only the non-``None`` fields, and persists the result
        inside a UoW so the transaction boundary lives in the use case
        rather than the repository.
        """
        async with self._uow_factory() as uow:
            current = await uow.preferences.find_by_user_key(DEFAULT_USER_KEY)
            if current is None:
                current = PlaybackPreferences.default_for(DEFAULT_USER_KEY)

            updated = current.apply_updates(
                audio_lang=input_dto.audio_lang,
                subtitle_lang=input_dto.subtitle_lang,
                subtitle_mode=input_dto.subtitle_mode,
                default_quality=input_dto.default_quality,
                speed=input_dto.speed,
            )
            saved = await uow.preferences.save(updated)

        return PreferencesOutput(
            audio_lang=saved.audio_lang,
            subtitle_lang=saved.subtitle_lang,
            subtitle_mode=saved.subtitle_mode.value,
            default_quality=saved.default_quality.value,
            speed=saved.speed.value,
        )


__all__ = ["UpdatePreferencesUseCase"]
