"""Movie repository interface."""

from abc import ABC, abstractmethod
from collections.abc import Sequence

from src.domain.media.entities.movie import Movie
from src.domain.media.value_objects import FilePath, MovieId


class MovieRepository(ABC):
    """Repository interface for Movie aggregate.

    This is a port in the hexagonal architecture pattern.
    Implementations (adapters) will be in the infrastructure layer.
    """

    @abstractmethod
    async def find_by_id(self, movie_id: MovieId) -> Movie | None:
        """Find a movie by its ID.

        Args:
            movie_id: The movie's external ID.

        Returns:
            The Movie if found, None otherwise.
        """
        ...

    @abstractmethod
    async def save(self, movie: Movie) -> Movie:
        """Persist a movie (create or update).

        Args:
            movie: The movie to save.

        Returns:
            The saved movie (with generated ID if new).
        """
        ...

    @abstractmethod
    async def delete(self, movie_id: MovieId) -> bool:
        """Delete a movie by ID.

        Args:
            movie_id: The movie's external ID.

        Returns:
            True if deleted, False if not found.
        """
        ...

    @abstractmethod
    async def list_all(self) -> Sequence[Movie]:
        """List all movies.

        Returns:
            Sequence of all movies.
        """
        ...

    @abstractmethod
    async def find_by_file_path(self, file_path: FilePath) -> Movie | None:
        """Find a movie by its file path.

        Args:
            file_path: The absolute file path.

        Returns:
            The Movie if found, None otherwise.
        """
        ...


__all__ = ["MovieRepository"]
