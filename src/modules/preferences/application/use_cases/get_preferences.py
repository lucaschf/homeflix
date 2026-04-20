"""GetPreferencesUseCase."""

from src.modules.preferences.application.dtos.preferences_dtos import PreferencesOutput
from src.modules.preferences.application.unit_of_work import PreferencesUnitOfWorkFactory
from src.modules.preferences.domain.entities import DEFAULT_USER_KEY, PlaybackPreferences


class GetPreferencesUseCase:
    """Return the current user's playback preferences.

    On first access (no row persisted yet) the domain factory
    ``PlaybackPreferences.default_for`` supplies the defaults — the
    use case stays thin and keeps no magic constants of its own.
    """

    def __init__(self, uow_factory: PreferencesUnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def execute(self) -> PreferencesOutput:
        """Fetch or default the user's playback preferences."""
        async with self._uow_factory() as uow:
            entity = await uow.preferences.find_by_user_key(DEFAULT_USER_KEY)
        if entity is None:
            entity = PlaybackPreferences.default_for(DEFAULT_USER_KEY)
        return _to_output(entity)


def _to_output(entity: PlaybackPreferences) -> PreferencesOutput:
    """Project the entity into the transport DTO."""
    return PreferencesOutput(
        audio_lang=entity.audio_lang,
        subtitle_lang=entity.subtitle_lang,
        subtitle_mode=entity.subtitle_mode.value,
        default_quality=entity.default_quality.value,
        speed=entity.speed.value,
    )


__all__ = ["GetPreferencesUseCase"]
