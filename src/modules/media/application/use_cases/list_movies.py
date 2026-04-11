"""ListMoviesUseCase - List movies in the library, paginated."""

from src.modules.media.application.dtos.movie_dtos import (
    ListMoviesInput,
    ListMoviesOutput,
    MovieSummaryOutput,
)
from src.modules.media.domain.entities import Movie
from src.modules.media.domain.repositories import MovieRepository


class ListMoviesUseCase:
    """List one page of movies using cursor-based pagination.

    Delegates the page query to ``MovieRepository.list_paginated`` and
    converts the resulting ``Movie`` entities into ``MovieSummaryOutput``
    DTOs. The cursor is passed through opaquely — the use case never
    decodes or encodes it, the repository owns that contract.

    Example:
        >>> use_case = ListMoviesUseCase(movie_repository)
        >>> result = await use_case.execute(ListMoviesInput(limit=20))
        >>> len(result.movies)
        20
        >>> result.has_more
        True
    """

    def __init__(self, movie_repository: MovieRepository) -> None:
        """Initialize the use case.

        Args:
            movie_repository: Repository for movie persistence.
        """
        self._movie_repository = movie_repository

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
        page = await self._movie_repository.list_paginated(
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
        """Convert Movie entity to summary output.

        Args:
            movie: The Movie entity to convert.
            lang: Language code for localized fields.

        Returns:
            MovieSummaryOutput with essential fields.
        """
        best = movie.best_file
        return MovieSummaryOutput(
            id=str(movie.id),
            title=movie.get_title(lang),
            year=movie.year.value,
            duration_formatted=movie.duration.format_hms(),
            synopsis=movie.get_synopsis(lang),
            poster_path=movie.poster_path.value if movie.poster_path else None,
            backdrop_path=movie.backdrop_path.value if movie.backdrop_path else None,
            resolution=best.resolution.value if best else None,
            variant_count=len(movie.files),
            available_resolutions=[r.value for r in movie.available_resolutions],
            genres=movie.get_genres(lang),
        )


__all__ = ["ListMoviesUseCase"]
