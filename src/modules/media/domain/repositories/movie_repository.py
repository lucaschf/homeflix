"""Movie repository interface."""

from abc import ABC, abstractmethod
from collections.abc import Sequence

from src.building_blocks.application.pagination import PaginatedResult
from src.modules.media.domain.entities.movie import Movie
from src.modules.media.domain.value_objects import FilePath, MovieId


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
    async def list_paginated(
        self,
        cursor: str | None,
        limit: int,
        *,
        include_total: bool = False,
    ) -> PaginatedResult[Movie]:
        """List movies in a single page using cursor-based pagination.

        The page is ordered by ``id DESC`` so the most recently
        inserted rows appear first. Internal autoincrement id is
        monotonic with insertion and matches "newest by ``created_at``"
        in practice because ``created_at`` is server-generated on
        insert and never edited later. The cursor snapshots only the
        ``id`` of the last row of the previous page and the next call
        resumes strictly after it. See
        ``src/building_blocks/application/pagination.py`` for the
        full justification (and the SQLite ``func.now()`` precision
        quirk that ruled out a ``(created_at, id)`` composite cursor).

        Args:
            cursor: Opaque token from the previous page's
                ``next_cursor``, or ``None`` for the first page.
                Invalid / undecodable cursors silently fall back to the
                first page so a stale token doesn't break a scroll.
            limit: Page size. Callers should clamp this in the route.
            include_total: When ``True`` the implementation runs an
                extra ``COUNT(*)`` to populate
                ``PaginatedResult.total_count``. Defaults to ``False``
                because the count is the most expensive part of the
                query and is rarely needed by infinite-scroll consumers.

        Returns:
            ``PaginatedResult`` containing the page items, the
            ``Pagination`` (next_cursor + has_more), and the optional
            total count.
        """
        ...

    @abstractmethod
    async def find_random(self, limit: int, *, with_backdrop: bool = False) -> Sequence[Movie]:
        """Return random movies, optionally filtering to those with backdrop.

        Args:
            limit: Maximum number of movies to return.
            with_backdrop: If True, only return movies with a backdrop_path.

        Returns:
            Sequence of randomly selected movies.
        """
        ...

    @abstractmethod
    async def find_by_ids(self, movie_ids: Sequence[MovieId]) -> dict[str, Movie]:
        """Find multiple movies by their IDs in a single query.

        Args:
            movie_ids: Sequence of movie external IDs.

        Returns:
            Dict mapping external ID string to Movie entity.
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
