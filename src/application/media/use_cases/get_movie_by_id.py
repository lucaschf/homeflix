"""GetMovieByIdUseCase - Retrieve a single movie by ID."""

from src.application.media.dtos.movie_dtos import GetMovieByIdInput, MovieOutput
from src.application.shared.exceptions import ResourceNotFoundException
from src.domain.media.entities import Movie
from src.domain.media.repositories import MovieRepository
from src.domain.media.value_objects import MovieId


class GetMovieByIdUseCase:
    """Retrieve a single movie by its external ID.

    This use case fetches a movie from the repository and returns
    it in a format suitable for API consumption.

    Example:
        >>> use_case = GetMovieByIdUseCase(movie_repository)
        >>> result = await use_case.execute(GetMovieByIdInput("mov_abc123"))
        >>> result.title
        'Inception'
    """

    def __init__(self, movie_repository: MovieRepository) -> None:
        """Initialize the use case.

        Args:
            movie_repository: Repository for movie persistence.
        """
        self._movie_repository = movie_repository

    async def execute(self, input_dto: GetMovieByIdInput) -> MovieOutput:
        """Execute the use case.

        Args:
            input_dto: Contains the movie_id to fetch.

        Returns:
            MovieOutput with all movie details.

        Raises:
            ResourceNotFoundException: If movie with given ID doesn't exist.
        """
        movie_id = MovieId(input_dto.movie_id)
        movie = await self._movie_repository.find_by_id(movie_id)

        if movie is None:
            raise ResourceNotFoundException.for_resource("Movie", input_dto.movie_id)

        return self._to_output(movie)

    @staticmethod
    def _to_output(movie: Movie) -> MovieOutput:
        """Convert Movie entity to output DTO.

        Args:
            movie: The Movie entity to convert.

        Returns:
            MovieOutput with all fields serialized.
        """
        primary = movie.primary_file
        return MovieOutput(
            id=str(movie.id),
            title=movie.title.value,
            original_title=movie.original_title.value if movie.original_title else None,
            year=movie.year.value,
            duration_seconds=movie.duration.value,
            duration_formatted=movie.duration.format_hms(),
            synopsis=movie.synopsis,
            poster_path=movie.poster_path.value if movie.poster_path else None,
            backdrop_path=movie.backdrop_path.value if movie.backdrop_path else None,
            genres=[g.value for g in movie.genres],
            file_path=primary.file_path.value if primary else None,
            file_size=primary.file_size if primary else None,
            resolution=primary.resolution.value if primary else None,
            tmdb_id=movie.tmdb_id,
            imdb_id=movie.imdb_id,
            created_at=movie.created_at.isoformat(),
            updated_at=movie.updated_at.isoformat(),
        )


__all__ = ["GetMovieByIdUseCase"]
