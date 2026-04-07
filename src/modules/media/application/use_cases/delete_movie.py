"""DeleteMovieUseCase - Soft-delete a movie by ID."""

from src.building_blocks.application.errors import ResourceNotFoundException
from src.modules.media.application.dtos.movie_dtos import DeleteMovieInput
from src.modules.media.domain.repositories import MovieRepository
from src.modules.media.domain.value_objects import MovieId


class DeleteMovieUseCase:
    """Soft-delete a movie by its external ID.

    Marks the movie as deleted in the database. The record is not
    physically removed, allowing for future recovery if needed.

    Example:
        >>> use_case = DeleteMovieUseCase(movie_repository)
        >>> await use_case.execute(DeleteMovieInput("mov_abc123"))
    """

    def __init__(self, movie_repository: MovieRepository) -> None:
        """Initialize the use case.

        Args:
            movie_repository: Repository for movie persistence.
        """
        self._movie_repository = movie_repository

    async def execute(self, input_dto: DeleteMovieInput) -> None:
        """Execute the use case.

        Args:
            input_dto: Contains the movie_id to delete.

        Raises:
            ResourceNotFoundException: If movie with given ID doesn't exist.
        """
        movie_id = MovieId(input_dto.movie_id)
        deleted = await self._movie_repository.delete(movie_id)

        if not deleted:
            raise ResourceNotFoundException.for_resource("Movie", input_dto.movie_id)


__all__ = ["DeleteMovieUseCase"]
