"""UpdatePreferencesUseCase."""

from src.modules.preferences.application.dtos.preferences_dtos import (
    PreferencesOutput,
    UpdatePreferencesInput,
)
from src.modules.preferences.application.unit_of_work import PreferencesUnitOfWorkFactory
from src.modules.preferences.domain.entities import PlaybackPreferences
from src.shared_kernel.value_objects.profile_id import ProfileId


class UpdatePreferencesUseCase:
    """Partially update (or create) the profile's playback preferences."""

    def __init__(self, uow_factory: PreferencesUnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def execute(self, input_dto: UpdatePreferencesInput) -> PreferencesOutput:
        """Upsert the profile's playback preferences.

        Loads the current record (or builds defaults on first save),
        applies only the non-``None`` fields, and persists the result
        inside a UoW so the transaction boundary lives in the use case
        rather than the repository.
        """
        profile_id = ProfileId(input_dto.profile_id)
        async with self._uow_factory() as uow:
            current = await uow.preferences.find_by_profile_id(profile_id)
            if current is None:
                current = PlaybackPreferences.default_for(profile_id)

            updated = current.apply_updates(
                audio_lang=input_dto.audio_lang,
                subtitle_lang=input_dto.subtitle_lang,
                subtitle_mode=input_dto.subtitle_mode,
                default_quality=input_dto.default_quality,
                speed=input_dto.speed,
                subtitle_appearance=input_dto.subtitle_appearance,
            )
            saved = await uow.preferences.save(updated)

        return PreferencesOutput.from_entity(saved)


__all__ = ["UpdatePreferencesUseCase"]
