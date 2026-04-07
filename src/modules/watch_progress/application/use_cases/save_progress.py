"""SaveProgressUseCase - Save or update watch progress."""

from src.modules.watch_progress.application.dtos import ProgressOutput, SaveProgressInput
from src.modules.watch_progress.domain.entities import WatchProgress
from src.modules.watch_progress.domain.repositories import WatchProgressRepository


class SaveProgressUseCase:
    """Save or update watch progress for a media item.

    Creates a new progress record if none exists, or updates the
    existing one. Automatically marks as completed at ≥90%.

    Example:
        >>> use_case = SaveProgressUseCase(progress_repository)
        >>> result = await use_case.execute(SaveProgressInput(
        ...     media_id="mov_abc123def456",
        ...     media_type="movie",
        ...     position_seconds=3600,
        ...     duration_seconds=7200,
        ... ))
    """

    def __init__(self, progress_repository: WatchProgressRepository) -> None:
        """Initialize the use case.

        Args:
            progress_repository: Repository for watch progress persistence.
        """
        self._repo = progress_repository

    async def execute(self, input_dto: SaveProgressInput) -> ProgressOutput:
        """Execute the use case.

        Args:
            input_dto: Progress data to save.

        Returns:
            The saved progress output.
        """
        existing = await self._repo.find_by_media_id(input_dto.media_id)

        if existing:
            progress = existing.update_position(
                position_seconds=input_dto.position_seconds,
                audio_track=input_dto.audio_track,
                subtitle_track=input_dto.subtitle_track,
            )
        else:
            progress = WatchProgress.create(
                media_id=input_dto.media_id,
                media_type=input_dto.media_type,
                position_seconds=input_dto.position_seconds,
                duration_seconds=input_dto.duration_seconds,
                audio_track=input_dto.audio_track,
                subtitle_track=input_dto.subtitle_track,
            )

        saved = await self._repo.save(progress)
        return _to_output(saved)


def _to_output(progress: WatchProgress) -> ProgressOutput:
    """Convert WatchProgress entity to output DTO."""
    return ProgressOutput(
        media_id=progress.media_id,
        media_type=progress.media_type,
        position_seconds=progress.position_seconds,
        duration_seconds=progress.duration_seconds,
        percentage=progress.percentage,
        status=progress.status,
        audio_track=progress.audio_track,
        subtitle_track=progress.subtitle_track,
        last_watched_at=progress.last_watched_at.isoformat(),
    )


__all__ = ["SaveProgressUseCase"]
