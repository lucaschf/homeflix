"""ListRecentlyAddedMoviesUseCase - Top N most recently added movies."""

from src.modules.media.application.dtos.movie_dtos import (
    ListRecentlyAddedMoviesInput,
    ListRecentlyAddedMoviesOutput,
)
from src.modules.media.application.unit_of_work import MediaUnitOfWorkFactory
from src.modules.media.application.use_cases._movie_summary_helpers import to_movie_summary


class ListRecentlyAddedMoviesUseCase:
    """Return the most recently added movies for the home-page carousel.

    Bounded "top N" projection — no cursor, no pagination metadata.
    The home-page carousel renders the full slice and the user goes
    to the catalog page if they want to keep browsing.

    Example:
        >>> use_case = ListRecentlyAddedMoviesUseCase(uow_factory)
        >>> result = await use_case.execute(ListRecentlyAddedMoviesInput(limit=20))
        >>> len(result.movies)
        20
    """

    def __init__(self, uow_factory: MediaUnitOfWorkFactory) -> None:
        """Initialize the use case.

        Args:
            uow_factory: Factory that opens a fresh media Unit of Work.
        """
        self._uow_factory = uow_factory

    async def execute(
        self, input_dto: ListRecentlyAddedMoviesInput
    ) -> ListRecentlyAddedMoviesOutput:
        """Execute the use case.

        Args:
            input_dto: ``limit`` (max items) and ``lang``.

        Returns:
            ``ListRecentlyAddedMoviesOutput`` with newest-first
            movie summaries.
        """
        async with self._uow_factory() as uow:
            movies = await uow.movies.list_recently_added(input_dto.limit)

        return ListRecentlyAddedMoviesOutput(
            movies=[to_movie_summary(movie, input_dto.lang) for movie in movies],
        )


__all__ = ["ListRecentlyAddedMoviesUseCase"]
