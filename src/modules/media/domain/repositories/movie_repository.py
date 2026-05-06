"""Movie repository interface."""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass

from src.building_blocks.application.pagination import PaginatedResult
from src.modules.media.domain.entities.movie import Movie
from src.modules.media.domain.value_objects import FilePath, Genre, MovieId


@dataclass(frozen=True)
class GenreRow:
    """Lightweight projection of one media row's genre columns.

    Used by ``list_genre_rows`` so genre aggregation across the full
    catalog doesn't have to load entities + their relationships. The
    parallel ``canonical_genres`` and ``localized_genres`` lists carry
    the same positional mapping the entity exposes via
    ``Entity.get_genres(lang)`` — index ``i`` of the localized list is
    the translation of index ``i`` of the canonical list.
    """

    canonical_genres: list[str]
    localized_genres: list[str]


class MovieRepository(ABC):
    """Repository interface for Movie aggregate.

    This is a port in the hexagonal architecture pattern.
    Implementations (adapters) will be in the infrastructure layer.
    """

    @abstractmethod
    async def find_by_id(
        self,
        movie_id: MovieId,
        *,
        allowed_library_ids: Sequence[str] | None = None,
    ) -> Movie | None:
        """Find a movie by its ID.

        Args:
            movie_id: The movie's external ID.
            allowed_library_ids: Optional per-profile ACL filter. When
                non-``None``, the lookup also requires the row's
                ``library_id`` to be in the supplied set; otherwise the
                method returns ``None`` even when a row with the id
                exists. ``None`` (default) applies no library filter —
                used by internal callers (scanner, cross-BC ACL
                adapters) that operate outside the per-profile catalog.

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
        allowed_library_ids: Sequence[str] | None = None,
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
            allowed_library_ids: Optional per-profile ACL filter. When
                non-``None``, both the page query and the optional
                ``COUNT(*)`` are restricted to rows whose
                ``library_id`` is in the supplied set. ``None``
                (default) applies no library filter.

        Returns:
            ``PaginatedResult`` containing the page items, the
            ``Pagination`` (next_cursor + has_more), and the optional
            total count.
        """
        ...

    @abstractmethod
    async def list_recently_added(
        self,
        limit: int,
        *,
        allowed_library_ids: Sequence[str] | None = None,
    ) -> Sequence[Movie]:
        """List the most recently added movies.

        Sorted by ``id DESC`` — internal autoincrement id is monotonic
        with insertion and matches "newest by ``created_at``" in
        practice because ``created_at`` is server-generated on insert
        and never edited later. Same justification as
        ``list_paginated``; this method is the bounded "top N" variant
        used by the home-page carousel where pagination would just be
        noise.

        Args:
            limit: Maximum number of movies to return.
            allowed_library_ids: Optional per-profile ACL filter. When
                non-``None``, results are restricted to rows whose
                ``library_id`` is in the supplied set. ``None``
                (default) applies no library filter.

        Returns:
            Sequence of recently added movies (excluding soft-deleted),
            most recent first.
        """
        ...

    @abstractmethod
    async def list_genre_rows(
        self,
        lang: str,
        *,
        allowed_library_ids: Sequence[str] | None = None,
    ) -> Sequence[GenreRow]:
        """Project the genre columns of every non-deleted row.

        This is the cheap input to cross-aggregate listings (e.g.
        ``ListGenresUseCase``) — only the ``genres`` and ``localized``
        columns are read so we don't pay the cost of loading file
        variants or any other relationships.

        Args:
            lang: Language code used to extract the localized genre
                names from the per-row ``localized`` JSON. Falls back
                to canonical English when no translation is present.
            allowed_library_ids: Optional per-profile ACL filter. When
                non-``None``, the projection is restricted to rows
                whose ``library_id`` is in the supplied set. ``None``
                (default) applies no library filter.

        Returns:
            One ``GenreRow`` per non-deleted movie. Order is not
            guaranteed.
        """
        ...

    @abstractmethod
    async def list_paginated_by_genre(
        self,
        genre: Genre,
        cursor: str | None,
        limit: int,
        *,
        allowed_library_ids: Sequence[str] | None = None,
    ) -> PaginatedResult[Movie]:
        """List movies belonging to a specific genre, paginated.

        Sorted by ``(LOWER(title) ASC, id ASC)`` so the catalog
        carousel renders alphabetically. The cursor is a
        ``(title, id)`` composite (see ``encode_title_cursor`` in the
        pagination building block) — the ``id`` tie-breaker keeps
        pagination stable when two rows share a title.

        The genre filter matches the canonical English genre name
        stored in ``MovieModel.genres`` (a comma-separated string).
        Localized display names live in the ``localized`` JSON column
        and are NOT used for filtering — the catalog "by genre"
        endpoint takes the canonical id and looks up the localized
        label client-side via ``ListGenresUseCase``.

        Args:
            genre: The canonical (English) genre to filter by.
            cursor: Opaque title cursor from the previous page, or
                ``None`` for the first page. Invalid cursors silently
                fall back to the first page.
            limit: Page size. The repository fetches ``limit + 1``
                rows and trims the sentinel to detect ``has_more``.
            allowed_library_ids: Optional per-profile ACL filter. When
                non-``None``, results are restricted to rows whose
                ``library_id`` is in the supplied set. ``None``
                (default) applies no library filter.

        Returns:
            ``PaginatedResult`` with the page items and pagination
            metadata. ``total_count`` is always ``None`` here — the
            catalog endpoint doesn't surface a per-genre count from
            this method (counts come from ``ListGenresUseCase``
            which aggregates across both movies and series).
        """
        ...

    @abstractmethod
    async def list_paginated_by_cast_member(
        self,
        actor_name: str,
        cursor: str | None,
        limit: int,
        *,
        allowed_library_ids: Sequence[str] | None = None,
    ) -> PaginatedResult[Movie]:
        """List movies whose cast includes a member named ``actor_name``.

        Sorted by ``(LOWER(title) ASC, id ASC)`` so the actor-page
        carousel renders alphabetically. The cursor is a
        ``(title, id)`` composite (see ``encode_title_cursor``) — same
        contract as ``list_paginated_by_genre``.

        Match is by exact name. The local catalog has no actor id
        (TMDB person ids aren't persisted yet, see CLAUDE.md
        roadmap), so two real people who share the same display name
        would collide. Acceptable trade-off for a personal-library
        scale catalog; can be tightened to a tmdb_person_id match
        without breaking the API surface (the route still receives a
        name and resolves to id internally).

        Args:
            actor_name: Exact display name of the cast member.
            cursor: Opaque title cursor from the previous page, or
                ``None`` for the first page. Invalid cursors silently
                fall back to the first page.
            limit: Page size. Implementations fetch ``limit + 1`` rows
                to detect ``has_more`` cheaply.
            allowed_library_ids: Optional per-profile ACL filter. When
                non-``None``, results are restricted to rows whose
                ``library_id`` is in the supplied set. ``None``
                (default) applies no library filter.

        Returns:
            ``PaginatedResult`` with the page items and pagination
            metadata. ``total_count`` is always ``None`` here.
        """
        ...

    @abstractmethod
    async def search(
        self,
        query: str,
        *,
        genre: str | None = None,
        year_min: int | None = None,
        year_max: int | None = None,
        limit: int = 20,
        allowed_library_ids: Sequence[str] | None = None,
    ) -> list[tuple[Movie, float]]:
        """Full-text search over title, synopsis, cast, and genres.

        Returns a list of ``(movie, rank)`` tuples ordered by relevance
        (lower rank = better match, matching FTS5 ``bm25()`` semantics).
        The ``rank`` value is infrastructure-specific; the use case only
        uses it for cross-type merge sorting.

        Args:
            query: The user's search string. Supports prefix matching
                (e.g. ``"incep"`` matches ``"Inception"``).
            genre: Optional canonical genre id filter.
            year_min: Optional inclusive lower bound on release year.
            year_max: Optional inclusive upper bound on release year.
            limit: Maximum items to return.
            allowed_library_ids: Optional per-profile ACL filter. When
                non-``None``, hits are restricted to rows whose
                ``library_id`` is in the supplied set. ``None``
                (default) applies no library filter.

        Returns:
            List of (Movie, rank) tuples, ordered by relevance.
        """
        ...

    @abstractmethod
    async def find_random(
        self,
        limit: int,
        *,
        with_backdrop: bool = False,
        allowed_library_ids: Sequence[str] | None = None,
    ) -> Sequence[Movie]:
        """Return random movies, optionally filtering to those with backdrop.

        Args:
            limit: Maximum number of movies to return.
            with_backdrop: If True, only return movies with a backdrop_path.
            allowed_library_ids: Optional per-profile ACL filter. When
                non-``None``, results are restricted to rows whose
                ``library_id`` is in the supplied set. ``None``
                (default) applies no library filter.

        Returns:
            Sequence of randomly selected movies.
        """
        ...

    @abstractmethod
    async def find_by_ids(
        self,
        movie_ids: Sequence[MovieId],
        *,
        allowed_library_ids: Sequence[str] | None = None,
    ) -> dict[str, Movie]:
        """Find multiple movies by their IDs in a single query.

        Args:
            movie_ids: Sequence of movie external IDs.
            allowed_library_ids: Optional per-profile ACL filter. When
                non-``None``, results are restricted to rows whose
                ``library_id`` is in the supplied set. ``None``
                (default) applies no library filter.

        Returns:
            Dict mapping external ID string to Movie entity.
        """
        ...

    @abstractmethod
    async def find_by_tmdb_ids(
        self,
        tmdb_ids: Sequence[int],
        *,
        allowed_library_ids: Sequence[str] | None = None,
    ) -> dict[int, Movie]:
        """Find movies whose ``tmdb_id`` is in ``tmdb_ids``.

        Used by the "you might also like" path: ``GetRelatedMovies``
        asks TMDB for related ids, then this method maps the subset
        present in the local catalog. Returning a dict keyed by
        ``tmdb_id`` lets the caller preserve the original TMDB
        ordering (which is by relevance) without paying for an extra
        traversal — the caller iterates ``tmdb_ids`` and looks each
        up in the dict.

        Soft-deleted rows are excluded.

        Args:
            tmdb_ids: TMDB movie ids to look up.
            allowed_library_ids: Optional per-profile ACL filter. When
                non-``None``, results are restricted to rows whose
                ``library_id`` is in the supplied set. ``None``
                (default) applies no library filter.

        Returns:
            Dict mapping ``tmdb_id`` int to ``Movie`` entity. Keys
            present in ``tmdb_ids`` but absent in the catalog simply
            don't appear in the result — no ``KeyError`` semantics.
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

    @abstractmethod
    async def find_missing_scrub_preview(self, limit: int) -> Sequence[Movie]:
        """Return up to ``limit`` movies that have no scrub-preview thumbnails yet.

        Used by the periodic backfill job to throttle work — every tick
        picks at most ``limit`` movies and generates their sprites,
        which keeps CPU bounded on large catalogs. Soft-deleted rows
        are excluded; movies without a primary file are included so the
        caller can decide to skip them.

        Args:
            limit: Maximum number of movies to return. Caller controls
                CPU/IO budget by tuning this with the run interval.

        Returns:
            Sequence of movies whose ``scrub_preview_path`` is null.
        """
        ...

    @abstractmethod
    async def count_under_paths(self, paths: Sequence[str]) -> int:
        """Count non-deleted movies whose file_path sits under any of ``paths``.

        Used to show per-library totals on the Libraries UI without an
        explicit ``library_id`` column — the association is implicit
        through the path prefix.

        Args:
            paths: Absolute directory paths to include. Matching is a
                string-prefix + separator check; both backslash and
                forward-slash variants are considered so the query
                works regardless of the OS the row was written on.

        Returns:
            Count of distinct movies whose primary file_path is under
            one of the supplied directories. ``0`` for an empty list.
        """
        ...


__all__ = ["GenreRow", "MovieRepository"]
