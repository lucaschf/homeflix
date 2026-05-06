"""DeleteMovieUseCase - Soft-delete a movie by ID."""

from src.building_blocks.application.errors import ResourceNotFoundException
from src.modules.media.application.dtos.movie_dtos import DeleteMovieInput
from src.modules.media.application.unit_of_work import MediaUnitOfWorkFactory
from src.modules.media.domain.value_objects import MovieId


class DeleteMovieUseCase:
    """Soft-delete a movie by its external ID.

    Marks the movie as deleted in the database. The record is not
    physically removed, allowing for future recovery if needed.

    Example:
        >>> use_case = DeleteMovieUseCase(uow_factory)
        >>> await use_case.execute(DeleteMovieInput("mov_abc123"))
    """

    def __init__(self, uow_factory: MediaUnitOfWorkFactory) -> None:
        """Initialize the use case.

        Args:
            uow_factory: Factory that opens a fresh media Unit of Work.
        """
        self._uow_factory = uow_factory

    async def execute(self, input_dto: DeleteMovieInput) -> None:
        """Execute the use case.

        Args:
            input_dto: Contains the movie_id to delete.

        Raises:
            ResourceNotFoundException: If movie with given ID doesn't exist.
        """
        movie_id = MovieId(input_dto.movie_id)
        async with self._uow_factory() as uow:
            deleted = await uow.movies.delete(movie_id)

        if not deleted:
            raise ResourceNotFoundException.for_resource("Movie", input_dto.movie_id)


__all__ = ["DeleteMovieUseCase"]
