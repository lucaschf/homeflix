"""ListRecentlyAddedSeriesUseCase - Top N most recently added series."""

from src.modules.media.application.dtos.series_dtos import (
    ListRecentlyAddedSeriesInput,
    ListRecentlyAddedSeriesOutput,
)
from src.modules.media.application.unit_of_work import MediaUnitOfWorkFactory
from src.modules.media.application.use_cases._series_summary_helpers import to_series_summary


class ListRecentlyAddedSeriesUseCase:
    """Return the most recently added series for the home-page carousel.

    Bounded "top N" projection — mirror of
    ``ListRecentlyAddedMoviesUseCase`` for the series side.

    Example:
        >>> use_case = ListRecentlyAddedSeriesUseCase(uow_factory)
        >>> result = await use_case.execute(ListRecentlyAddedSeriesInput(limit=20))
        >>> len(result.series)
        20
    """

    def __init__(self, uow_factory: MediaUnitOfWorkFactory) -> None:
        """Initialize the use case.

        Args:
            uow_factory: Factory that opens a fresh media Unit of Work.
        """
        self._uow_factory = uow_factory

    async def execute(
        self, input_dto: ListRecentlyAddedSeriesInput
    ) -> ListRecentlyAddedSeriesOutput:
        """Execute the use case.

        Args:
            input_dto: ``limit`` (max items) and ``lang``.

        Returns:
            ``ListRecentlyAddedSeriesOutput`` with newest-first
            series summaries.
        """
        async with self._uow_factory() as uow:
            series_list = await uow.series.list_recently_added(input_dto.limit)

        return ListRecentlyAddedSeriesOutput(
            series=[to_series_summary(s, input_dto.lang) for s in series_list],
        )


__all__ = ["ListRecentlyAddedSeriesUseCase"]
