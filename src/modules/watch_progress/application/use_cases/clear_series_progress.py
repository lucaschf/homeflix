"""ClearSeriesProgressUseCase - Clear all episode progress for a series."""

from dataclasses import dataclass

from src.modules.watch_progress.domain.repositories import WatchProgressRepository


@dataclass(frozen=True)
class ClearSeriesProgressInput:
    """Input for ClearSeriesProgressUseCase.

    Attributes:
        series_id: External series ID (``ser_xxx`` format).
    """

    series_id: str


class ClearSeriesProgressUseCase:
    """Soft-delete all episode progress entries for a series.

    Used by the "dismiss from Continue Watching" action so that
    removing a series clears ALL its episode progress at once —
    otherwise deleting one episode's progress just surfaces the
    next in-progress episode and the series reappears.
    """

    def __init__(self, progress_repository: WatchProgressRepository) -> None:
        self._repo = progress_repository

    async def execute(self, input_dto: ClearSeriesProgressInput) -> int:
        """Execute the use case.

        Args:
            input_dto: Contains the series_id.

        Returns:
            Number of episode progress records soft-deleted.
        """
        return await self._repo.delete_by_series(input_dto.series_id)


__all__ = ["ClearSeriesProgressUseCase"]
