"""SaveProgressUseCase - Save or update watch progress."""

from src.modules.watch_progress.application.dtos import ProgressOutput, SaveProgressInput
from src.modules.watch_progress.application.unit_of_work import (
    WatchProgressUnitOfWorkFactory,
)
from src.modules.watch_progress.domain.entities import WatchProgress
from src.modules.watch_progress.domain.value_objects import WatchableMediaType


class SaveProgressUseCase:
    """Save or update watch progress for a media item.

    Creates a new progress record if none exists, or updates the
    existing one. Automatically marks as completed at ≥90%.
    """

    def __init__(self, uow_factory: WatchProgressUnitOfWorkFactory) -> None:
        """Initialize the use case.

        Args:
            uow_factory: Factory that opens a fresh watch progress UoW.
        """
        self._uow_factory = uow_factory

    async def execute(self, input_dto: SaveProgressInput) -> ProgressOutput:
        """Execute the use case.

        Args:
            input_dto: Progress data to save.

        Returns:
            The saved progress output.
        """
        async with self._uow_factory() as uow:
            existing = await uow.progress.find_by_media_id(input_dto.media_id)

            if existing:
                progress = existing.update_position(
                    position_seconds=input_dto.position_seconds,
                    duration_seconds=input_dto.duration_seconds,
                    audio_track=input_dto.audio_track,
                    subtitle_track=input_dto.subtitle_track,
                )
            else:
                progress = WatchProgress.create(
                    media_id=input_dto.media_id,
                    media_type=WatchableMediaType(input_dto.media_type),
                    position_seconds=input_dto.position_seconds,
                    duration_seconds=input_dto.duration_seconds,
                    audio_track=input_dto.audio_track,
                    subtitle_track=input_dto.subtitle_track,
                )

            saved = await uow.progress.save(progress)
        return ProgressOutput.from_entity(saved)


__all__ = ["SaveProgressUseCase"]
