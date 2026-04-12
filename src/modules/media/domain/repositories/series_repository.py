"""Series repository interface."""

from abc import ABC, abstractmethod
from collections.abc import Sequence

from src.building_blocks.application.pagination import PaginatedResult
from src.modules.media.domain.entities.series import Series
from src.modules.media.domain.repositories.movie_repository import GenreRow
from src.modules.media.domain.value_objects import EpisodeId, FilePath, Genre, SeriesId, Title


class SeriesRepository(ABC):
    """Repository interface for Series aggregate.

    This is a port in the hexagonal architecture pattern.
    Implementations (adapters) will be in the infrastructure layer.
    """

    @abstractmethod
    async def find_by_id(self, series_id: SeriesId) -> Series | None:
        """Find a series by its ID (includes seasons and episodes).

        Args:
            series_id: The series' external ID.

        Returns:
            The Series if found, None otherwise.
        """
        ...

    @abstractmethod
    async def save(self, series: Series) -> Series:
        """Persist a series with all its seasons and episodes.

        Args:
            series: The series to save.

        Returns:
            The saved series (with generated IDs if new).
        """
        ...

    @abstractmethod
    async def delete(self, series_id: SeriesId) -> bool:
        """Delete a series and all its seasons/episodes.

        Args:
            series_id: The series' external ID.

        Returns:
            True if deleted, False if not found.
        """
        ...

    @abstractmethod
    async def list_all(self) -> Sequence[Series]:
        """List all series (may return shallow objects without episodes).

        Returns:
            Sequence of all series.
        """
        ...

    @abstractmethod
    async def list_paginated(
        self,
        cursor: str | None,
        limit: int,
        *,
        include_total: bool = False,
    ) -> PaginatedResult[Series]:
        """List series in a single page using cursor-based pagination.

        Sorted by ``id DESC`` so the most recently inserted rows
        appear first. Internal autoincrement id is monotonic with
        insertion and matches "newest by ``created_at``" in practice
        because ``created_at`` is server-generated on insert and never
        edited later. The cursor snapshots only the ``id`` of the last
        row of the previous page. See
        ``src/building_blocks/application/pagination.py`` for the
        full justification (and the SQLite ``func.now()`` precision
        quirk that ruled out a ``(created_at, id)`` composite cursor).

        Args:
            cursor: Opaque token from the previous page's
                ``next_cursor``, or ``None`` for the first page.
                Invalid / undecodable cursors silently fall back to
                the first page.
            limit: Page size. Callers should clamp this in the route.
            include_total: When ``True`` the implementation runs an
                extra ``COUNT(*)`` to populate
                ``PaginatedResult.total_count``. Defaults to ``False``.

        Returns:
            ``PaginatedResult`` containing the page items, the
            ``Pagination`` (next_cursor + has_more), and the optional
            total count.
        """
        ...

    @abstractmethod
    async def list_genre_rows(self, lang: str) -> Sequence[GenreRow]:
        """Project the genre columns of every non-deleted series row.

        Same contract as ``MovieRepository.list_genre_rows`` — see
        that method for the full description. Used by the catalog
        genres aggregation use case to compute counts and resolve
        localized labels without loading the full series hierarchy.
        """
        ...

    @abstractmethod
    async def list_paginated_by_genre(
        self,
        genre: Genre,
        cursor: str | None,
        limit: int,
    ) -> PaginatedResult[Series]:
        """List series belonging to a specific genre, paginated.

        Sorted by ``(LOWER(title) ASC, id ASC)``. Same contract as
        ``MovieRepository.list_paginated_by_genre`` — see that method
        for the full description of the cursor format and the genre
        filter (whole-word LIKE on the comma-separated ``genres``
        column).
        """
        ...

    @abstractmethod
    async def find_random(self, limit: int, *, with_backdrop: bool = False) -> Sequence[Series]:
        """Return random series, optionally filtering to those with backdrop.

        Args:
            limit: Maximum number of series to return.
            with_backdrop: If True, only return series with a backdrop_path.

        Returns:
            Sequence of randomly selected series.
        """
        ...

    @abstractmethod
    async def find_by_ids(self, series_ids: Sequence[SeriesId]) -> dict[str, Series]:
        """Find multiple series by their IDs in a single query.

        Args:
            series_ids: Sequence of series external IDs.

        Returns:
            Dict mapping external ID string to Series entity.
        """
        ...

    @abstractmethod
    async def find_by_episode_id(self, episode_id: EpisodeId) -> Series | None:
        """Find a series containing an episode with this ID.

        Args:
            episode_id: The episode's external ID.

        Returns:
            The Series if found, None otherwise.
        """
        ...

    @abstractmethod
    async def find_by_title(self, title: Title) -> Series | None:
        """Find a series by its title (case-insensitive).

        Args:
            title: The series title to search for.

        Returns:
            The Series if found, None otherwise.
        """
        ...

    @abstractmethod
    async def find_by_file_path(self, file_path: FilePath) -> Series | None:
        """Find a series containing an episode with this file path.

        Args:
            file_path: The absolute file path.

        Returns:
            The Series if found, None otherwise.
        """
        ...


__all__ = ["SeriesRepository"]
