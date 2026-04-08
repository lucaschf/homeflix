"""ListSeriesUseCase - List all series in the library."""

from src.modules.media.application.dtos.series_dtos import (
    ListSeriesInput,
    ListSeriesOutput,
    SeriesSummaryOutput,
)
from src.modules.media.domain.entities import Series
from src.modules.media.domain.repositories import SeriesRepository


class ListSeriesUseCase:
    """List all series in the library.

    Returns a list of series summaries suitable for grid/list display.
    Does not include full episode hierarchy for performance.

    Example:
        >>> use_case = ListSeriesUseCase(series_repository)
        >>> result = await use_case.execute(ListSeriesInput())
        >>> len(result.series)
        15
    """

    def __init__(self, series_repository: SeriesRepository) -> None:
        """Initialize the use case.

        Args:
            series_repository: Repository for series persistence.
        """
        self._series_repository = series_repository

    async def execute(self, input_dto: ListSeriesInput) -> ListSeriesOutput:
        """Execute the use case.

        Args:
            input_dto: Contains optional limit.

        Returns:
            ListSeriesOutput with series summaries.
        """
        all_series = await self._series_repository.list_all()

        total_count = len(all_series)

        if input_dto.limit is not None:
            all_series = all_series[: input_dto.limit]

        return ListSeriesOutput(
            series=[self._to_summary(s) for s in all_series],
            total_count=total_count,
        )

    @staticmethod
    def _to_summary(series: Series) -> SeriesSummaryOutput:
        """Convert Series entity to summary output.

        Args:
            series: The Series entity to convert.

        Returns:
            SeriesSummaryOutput with essential fields.
        """
        return SeriesSummaryOutput(
            id=str(series.id),
            title=series.title.value,
            start_year=series.start_year.value,
            end_year=series.end_year.value if series.end_year else None,
            is_ongoing=series.is_ongoing,
            synopsis=series.synopsis,
            poster_path=series.poster_path.value if series.poster_path else None,
            backdrop_path=series.backdrop_path.value if series.backdrop_path else None,
            season_count=series.season_count,
            total_episodes=series.total_episodes,
            genres=[g.value for g in series.genres],
        )


__all__ = ["ListSeriesUseCase"]
