"""GetPreferencesUseCase."""

from src.modules.preferences.application.dtos.preferences_dtos import (
    GetPreferencesInput,
    PreferencesOutput,
)
from src.modules.preferences.application.unit_of_work import PreferencesUnitOfWorkFactory
from src.modules.preferences.domain.entities import PlaybackPreferences
from src.shared_kernel.value_objects.profile_id import ProfileId


class GetPreferencesUseCase:
    """Return the current profile's playback preferences.

    On first access (no row persisted yet) the domain factory
    ``PlaybackPreferences.default_for`` supplies the defaults — the
    use case stays thin and keeps no magic constants of its own.
    """

    def __init__(self, uow_factory: PreferencesUnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def execute(self, input_dto: GetPreferencesInput) -> PreferencesOutput:
        """Fetch or default the profile's playback preferences."""
        profile_id = ProfileId(input_dto.profile_id)
        async with self._uow_factory() as uow:
            entity = await uow.preferences.find_by_profile_id(profile_id)
        if entity is None:
            entity = PlaybackPreferences.default_for(profile_id)
        return _to_output(entity)


def _to_output(entity: PlaybackPreferences) -> PreferencesOutput:
    """Project the entity into the transport DTO."""
    return PreferencesOutput(
        audio_lang=entity.audio_lang.value,
        subtitle_lang=entity.subtitle_lang.value,
        subtitle_mode=entity.subtitle_mode.value,
        default_quality=entity.default_quality.value,
        speed=entity.speed.value,
    )


__all__ = ["GetPreferencesUseCase"]
