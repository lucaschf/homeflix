"""ClearSeriesProgressUseCase - Clear all episode progress for a series."""

from dataclasses import dataclass

from src.modules.watch_progress.application.unit_of_work import (
    WatchProgressUnitOfWorkFactory,
)
from src.shared_kernel.value_objects.media_id import SeriesId
from src.shared_kernel.value_objects.profile_id import ProfileId


@dataclass(frozen=True)
class ClearSeriesProgressInput:
    """Input for ClearSeriesProgressUseCase."""

    profile_id: str
    series_id: str


class ClearSeriesProgressUseCase:
    """Soft-delete every episode progress for a series in one profile.

    Used by the "dismiss from Continue Watching" action so that
    removing a series clears ALL its episode progress at once —
    otherwise deleting one episode's progress just surfaces the
    next in-progress episode and the series reappears. The deletion
    only touches rows owned by the caller's profile.
    """

    def __init__(self, uow_factory: WatchProgressUnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def execute(self, input_dto: ClearSeriesProgressInput) -> int:
        """Soft-delete every episode-progress row for the series, return count."""
        async with self._uow_factory() as uow:
            return await uow.progress.delete_by_series(
                SeriesId(input_dto.series_id),
                ProfileId(input_dto.profile_id),
            )


__all__ = ["ClearSeriesProgressInput", "ClearSeriesProgressUseCase"]
