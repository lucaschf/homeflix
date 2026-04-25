"""ListMoviesUseCase - List movies in the library, paginated."""

from src.modules.media.application.dtos.movie_dtos import (
    ListMoviesInput,
    ListMoviesOutput,
    MovieSummaryOutput,
)
from src.modules.media.application.unit_of_work import MediaUnitOfWorkFactory
from src.modules.media.application.use_cases._movie_summary_helpers import to_movie_summary
from src.modules.media.domain.entities import Movie


class ListMoviesUseCase:
    """List one page of movies using cursor-based pagination.

    Delegates the page query to ``MovieRepository.list_paginated`` and
    converts the resulting ``Movie`` entities into ``MovieSummaryOutput``
    DTOs. The cursor is passed through opaquely — the use case never
    decodes or encodes it, the repository owns that contract.

    Example:
        >>> use_case = ListMoviesUseCase(uow_factory)
        >>> result = await use_case.execute(ListMoviesInput(limit=20))
        >>> len(result.movies)
        20
        >>> result.has_more
        True
    """

    def __init__(self, uow_factory: MediaUnitOfWorkFactory) -> None:
        """Initialize the use case.

        Args:
            uow_factory: Factory that opens a fresh media Unit of Work.
        """
        self._uow_factory = uow_factory

    async def execute(self, input_dto: ListMoviesInput) -> ListMoviesOutput:
        """Execute the use case.

        Args:
            input_dto: ``cursor`` (opaque), ``limit``, ``include_total``,
                and ``lang``.

        Returns:
            ``ListMoviesOutput`` with the page items, the next cursor,
            ``has_more``, and an optional ``total_count`` (only when
            ``include_total=True``).
        """
        async with self._uow_factory() as uow:
            page = await uow.movies.list_paginated(
                cursor=input_dto.cursor,
                limit=input_dto.limit,
                include_total=input_dto.include_total,
            )

        return ListMoviesOutput(
            movies=[self._to_summary(movie, input_dto.lang) for movie in page.items],
            next_cursor=page.pagination.next_cursor,
            has_more=page.pagination.has_more,
            total_count=page.total_count,
        )

    @staticmethod
    def _to_summary(movie: Movie, lang: str = "en") -> MovieSummaryOutput:
        """Convert Movie entity to summary output."""
        return to_movie_summary(movie, lang)


__all__ = ["ListMoviesUseCase"]
