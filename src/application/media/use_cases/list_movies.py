"""ListMoviesUseCase - List all movies in the library."""

from src.application.media.dtos.movie_dtos import (
    ListMoviesInput,
    ListMoviesOutput,
    MovieSummaryOutput,
)
from src.domain.media.entities import Movie
from src.domain.media.repositories import MovieRepository


class ListMoviesUseCase:
    """List all movies in the library.

    Returns a list of movie summaries suitable for grid/list display.

    Example:
        >>> use_case = ListMoviesUseCase(movie_repository)
        >>> result = await use_case.execute(ListMoviesInput(limit=20))
        >>> len(result.movies)
        20
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
            input_dto: Contains optional limit parameter.

        Returns:
            ListMoviesOutput with movie summaries and count.
        """
        movies = await self._movie_repository.list_all()

        total_count = len(movies)

        if input_dto.limit is not None:
            movies = movies[: input_dto.limit]

        return ListMoviesOutput(
            movies=[self._to_summary(movie) for movie in movies],
            total_count=total_count,
        )

    @staticmethod
    def _to_summary(movie: Movie) -> MovieSummaryOutput:
        """Convert Movie entity to summary output.

        Args:
            movie: The Movie entity to convert.

        Returns:
            MovieSummaryOutput with essential fields.
        """
        return MovieSummaryOutput(
            id=str(movie.id),
            title=movie.title.value,
            year=movie.year.value,
            duration_formatted=movie.duration.format_hms(),
            poster_path=movie.poster_path.value if movie.poster_path else None,
            resolution=movie.resolution.value,
            genres=[g.value for g in movie.genres],
        )


__all__ = ["ListMoviesUseCase"]
