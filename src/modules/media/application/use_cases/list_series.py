"""ListSeriesUseCase - List series in the library, paginated."""

from src.modules.media.application.dtos.series_dtos import (
    ListSeriesInput,
    ListSeriesOutput,
    SeriesSummaryOutput,
)
from src.modules.media.domain.entities import Series
from src.modules.media.domain.repositories import SeriesRepository


class ListSeriesUseCase:
    """List one page of series using cursor-based pagination.

    Delegates the page query to ``SeriesRepository.list_paginated`` and
    converts the resulting ``Series`` entities into
    ``SeriesSummaryOutput`` DTOs. The cursor is passed through
    opaquely.

    Example:
        >>> use_case = ListSeriesUseCase(series_repository)
        >>> result = await use_case.execute(ListSeriesInput())
        >>> len(result.series)
        20
        >>> result.has_more
        True
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
            input_dto: ``cursor`` (opaque), ``limit``, ``include_total``,
                and ``lang``.

        Returns:
            ``ListSeriesOutput`` with the page items, the next cursor,
            ``has_more``, and an optional ``total_count`` (only when
            ``include_total=True``).
        """
        page = await self._series_repository.list_paginated(
            cursor=input_dto.cursor,
            limit=input_dto.limit,
            include_total=input_dto.include_total,
        )

        return ListSeriesOutput(
            series=[self._to_summary(s, input_dto.lang) for s in page.items],
            next_cursor=page.pagination.next_cursor,
            has_more=page.pagination.has_more,
            total_count=page.total_count,
        )

    @staticmethod
    def _to_summary(series: Series, lang: str = "en") -> SeriesSummaryOutput:
        """Convert Series entity to summary output.

        Args:
            series: The Series entity to convert.
            lang: Language code for localized fields.

        Returns:
            SeriesSummaryOutput with essential fields.
        """
        return SeriesSummaryOutput(
            id=str(series.id),
            title=series.get_title(lang),
            start_year=series.start_year.value,
            end_year=series.end_year.value if series.end_year else None,
            is_ongoing=series.is_ongoing,
            synopsis=series.get_synopsis(lang),
            poster_path=series.poster_path.value if series.poster_path else None,
            backdrop_path=series.backdrop_path.value if series.backdrop_path else None,
            season_count=series.season_count,
            total_episodes=series.total_episodes,
            genres=series.get_genres(lang),
        )


__all__ = ["ListSeriesUseCase"]
