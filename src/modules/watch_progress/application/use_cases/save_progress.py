"""SaveProgressUseCase - Save or update watch progress."""

from src.modules.watch_progress.application.dtos import ProgressOutput, SaveProgressInput
from src.modules.watch_progress.application.unit_of_work import (
    WatchProgressUnitOfWorkFactory,
)
from src.modules.watch_progress.domain.entities import WatchProgress
from src.modules.watch_progress.domain.value_objects import (
    SubtitlePreference,
    WatchableMediaId,
    WatchableMediaType,
)
from src.shared_kernel.value_objects.profile_id import ProfileId


class SaveProgressUseCase:
    """Save or update watch progress for a media item, scoped to one profile."""

    def __init__(self, uow_factory: WatchProgressUnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def execute(self, input_dto: SaveProgressInput) -> ProgressOutput:
        """Persist progress for the caller's profile."""
        profile_id = ProfileId(input_dto.profile_id)
        media_id = WatchableMediaId(input_dto.media_id)
        subtitle_track = SubtitlePreference.from_wire(input_dto.subtitle_track)
        async with self._uow_factory() as uow:
            existing = await uow.progress.find_by_media_id(media_id, profile_id)

            if existing:
                progress = existing.update_position(
                    position_seconds=input_dto.position_seconds,
                    duration_seconds=input_dto.duration_seconds,
                    audio_track=input_dto.audio_track,
                    subtitle_track=subtitle_track,
                )
            else:
                progress = WatchProgress.create(
                    profile_id=profile_id,
                    media_id=media_id,
                    media_type=WatchableMediaType(input_dto.media_type),
                    position_seconds=input_dto.position_seconds,
                    duration_seconds=input_dto.duration_seconds,
                    audio_track=input_dto.audio_track,
                    subtitle_track=subtitle_track,
                )

            saved = await uow.progress.save(progress)
        return ProgressOutput.from_entity(saved)


__all__ = ["SaveProgressUseCase"]
