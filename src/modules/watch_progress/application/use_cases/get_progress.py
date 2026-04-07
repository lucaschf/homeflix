"""GetProgressUseCase - Get watch progress for a media item."""

from src.modules.watch_progress.application.dtos import GetProgressInput, ProgressOutput
from src.modules.watch_progress.domain.entities import WatchProgress
from src.modules.watch_progress.domain.repositories import WatchProgressRepository


class GetProgressUseCase:
    """Retrieve watch progress for a single media item.

    Returns None if no progress exists (does not raise 404).

    Example:
        >>> use_case = GetProgressUseCase(progress_repository)
        >>> result = await use_case.execute(GetProgressInput("mov_abc123def456"))
    """

    def __init__(self, progress_repository: WatchProgressRepository) -> None:
        """Initialize the use case.

        Args:
            progress_repository: Repository for watch progress persistence.
        """
        self._repo = progress_repository

    async def execute(self, input_dto: GetProgressInput) -> ProgressOutput | None:
        """Execute the use case.

        Args:
            input_dto: Contains the media_id to look up.

        Returns:
            ProgressOutput if found, None otherwise.
        """
        progress = await self._repo.find_by_media_id(input_dto.media_id)
        if progress is None:
            return None
        return _to_output(progress)


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


__all__ = ["GetProgressUseCase"]
