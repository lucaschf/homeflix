"""Series repository interfaces.

``SeriesCatalogRepository`` is the lean catalog port — CRUD, search,
pagination, episode lookup, stats — the stable core. The job-oriented
concerns are segregated into role-interfaces (ADR-033):
:class:`~...scrub_preview_repository.SeriesScrubPreviewRepository`,
:class:`~...artwork_mirror_repository.SeriesArtworkMirrorRepository`,
:class:`~...intro_detection_repository.SeriesIntroDetectionRepository`, and
:class:`~...credits_detection_repository.SeriesCreditsDetectionRepository`.

``SeriesRepository`` is the composite facade the ``MediaUnitOfWork`` exposes
and the SQLAlchemy adapter implements — a single class against the
``series`` / ``seasons`` / ``episodes`` tables satisfying every role
(ADR-033 §Decisão).
"""

from abc import ABC, abstractmethod
from collections.abc import Sequence

from src.building_blocks.domain.pagination import PaginatedResult
from src.modules.media.domain.entities.episode import Episode
from src.modules.media.domain.entities.series import Series
from src.modules.media.domain.repositories.artwork_mirror_repository import (
    SeriesArtworkMirrorRepository,
)
from src.modules.media.domain.repositories.credits_detection_repository import (
    SeriesCreditsDetectionRepository,
)
from src.modules.media.domain.repositories.intro_detection_repository import (
    SeriesIntroDetectionRepository,
)
from src.modules.media.domain.repositories.movie_repository import GenreRow
from src.modules.media.domain.repositories.scrub_preview_repository import (
    SeriesScrubPreviewRepository,
)
from src.modules.media.domain.value_objects import (
    CatalogSort,
    EpisodeId,
    FilePath,
    Genre,
    SeriesId,
    Title,
)
from src.shared_kernel.value_objects.library_id import LibraryId


class SeriesCatalogRepository(ABC):
    """Lean catalog port for the Series aggregate.

    CRUD, search, pagination, episode lookup, and stats — the stable
    core that every catalog consumer depends on. Job-oriented concerns
    (artwork mirror, intro detection, credits detection, scrub preview)
    live in their own role-interfaces (ADR-033).
    """

    @abstractmethod
    async def find_by_id(
        self,
        series_id: SeriesId,
        *,
        allowed_library_ids: Sequence[LibraryId] | None = None,
    ) -> Series | None:
        """Find a series by its ID (includes seasons and episodes).

        Args:
            series_id: The series' external ID.
            allowed_library_ids: Optional per-profile ACL filter. When
                non-``None``, the lookup also requires the row's
                ``library_id`` to be in the supplied set; otherwise the
                method returns ``None`` even when a row with the id
                exists. ``None`` (default) applies no library filter —
                used by internal callers (scanner, cross-BC ACL
                adapters) that operate outside the per-profile catalog.

        Returns:
            The Series if found, None otherwise.
        """
        ...

    @abstractmethod
    async def find_needs_enrichment_review(
        self,
        *,
        allowed_library_ids: Sequence[LibraryId] | None = None,
    ) -> Sequence[Series]:
        """Return series flagged for admin enrichment review.

        Backs the ``GET /admin/series/needs-review`` listing.
        Soft-deleted rows are excluded. The set is expected to be
        small so no pagination — caller orders by ``updated_at`` so
        newest-flagged float up.

        Args:
            allowed_library_ids: Optional per-profile ACL filter. When
                non-``None``, restricts to rows owned by libraries in
                the set; ``None`` means no library filter (current
                admin endpoint passes ``None``).

        Returns:
            Sequence of flagged series.
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
        allowed_library_ids: Sequence[LibraryId] | None = None,
        library_id: str | None = None,
        has_tmdb_id: bool | None = None,
        q: str | None = None,
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
            allowed_library_ids: Optional per-profile ACL filter. When
                non-``None``, both the page query and the optional
                ``COUNT(*)`` are restricted to rows whose
                ``library_id`` is in the supplied set. ``None``
                (default) applies no library filter.
            library_id: Optional admin filter — restrict to a single
                library (composes with ``allowed_library_ids``).
            has_tmdb_id: Optional admin filter — ``True`` keeps only
                enriched rows, ``False`` only un-enriched, ``None``
                applies no filter.
            q: Optional case-insensitive substring match against
                ``title`` / ``original_title``. ``None`` or an empty /
                whitespace-only string applies no filter.

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
        allowed_library_ids: Sequence[LibraryId] | None = None,
    ) -> Sequence[Series]:
        """List the most recently added series.

        Sorted by ``id DESC`` — same justification as
        ``MovieCatalogRepository.list_recently_added``. The home-page
        carousel consumes a fixed top N, so no cursor or pagination
        metadata is involved.

        Args:
            limit: Maximum number of series to return.
            allowed_library_ids: Optional per-profile ACL filter. When
                non-``None``, results are restricted to rows whose
                ``library_id`` is in the supplied set. ``None``
                (default) applies no library filter.

        Returns:
            Sequence of recently added series (excluding soft-deleted),
            most recent first.
        """
        ...

    @abstractmethod
    async def list_genre_rows(
        self,
        lang: str,
        *,
        allowed_library_ids: Sequence[LibraryId] | None = None,
    ) -> Sequence[GenreRow]:
        """Project the genre columns of every non-deleted series row.

        Same contract as ``MovieCatalogRepository.list_genre_rows`` — see
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
        *,
        sort: CatalogSort = CatalogSort.TITLE_ASC,
        lang: str = "en",
        allowed_library_ids: Sequence[LibraryId] | None = None,
    ) -> PaginatedResult[Series]:
        """List series belonging to a specific genre, paginated.

        Ordering is chosen by ``sort`` (see :class:`CatalogSort`),
        defaulting to ``(LOWER(COALESCE(localized[lang].title, title))
        ASC, id ASC)``. For ``year_*`` sorts the series ``start_year``
        is the release-year key. Same contract as
        ``MovieCatalogRepository.list_paginated_by_genre`` — see that
        method for the full description of the sort-bound cursor format and
        the genre filter (whole-word LIKE on the comma-separated
        ``genres`` column).
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
        allowed_library_ids: Sequence[LibraryId] | None = None,
    ) -> list[tuple[Series, float]]:
        """Full-text search over title, synopsis, and genres.

        Same contract as ``MovieCatalogRepository.search`` — returns
        ``(series, rank)`` tuples ordered by relevance.
        """
        ...

    @abstractmethod
    async def find_random(
        self,
        limit: int,
        *,
        with_backdrop: bool = False,
        allowed_library_ids: Sequence[LibraryId] | None = None,
        genres: Sequence[Genre] | None = None,
        exclude_ids: Sequence[SeriesId] | None = None,
    ) -> Sequence[Series]:
        """Return random series, optionally filtering to those with backdrop.

        Args:
            limit: Maximum number of series to return.
            with_backdrop: If True, only return series with a backdrop_path.
            allowed_library_ids: Optional per-profile ACL filter. When
                non-``None``, results are restricted to rows whose
                ``library_id`` is in the supplied set. ``None``
                (default) applies no library filter.
            genres: Optional canonical (English) genres. When
                non-empty, only series tagged with **at least one** of
                them are eligible. ``None`` or empty applies no genre
                filter.
            exclude_ids: Optional series ids to leave out of the pool
                (e.g. titles the profile already watched).

        Returns:
            Sequence of randomly selected series.
        """
        ...

    @abstractmethod
    async def find_by_ids(
        self,
        series_ids: Sequence[SeriesId],
        *,
        allowed_library_ids: Sequence[LibraryId] | None = None,
    ) -> dict[str, Series]:
        """Find multiple series by their IDs in a single query.

        Args:
            series_ids: Sequence of series external IDs.
            allowed_library_ids: Optional per-profile ACL filter. When
                non-``None``, results are restricted to rows whose
                ``library_id`` is in the supplied set. ``None``
                (default) applies no library filter.

        Returns:
            Dict mapping external ID string to Series entity.
        """
        ...

    @abstractmethod
    async def find_by_tmdb_ids(
        self,
        tmdb_ids: Sequence[int],
        *,
        allowed_library_ids: Sequence[LibraryId] | None = None,
    ) -> dict[int, Series]:
        """Find series whose ``tmdb_id`` matches any of ``tmdb_ids``.

        Used by ``GetRelatedSeries`` to resolve the subset of TMDB's
        recommendation list that exists locally. Returning a dict
        keyed by ``tmdb_id`` lets the caller preserve TMDB's
        relevance ordering by iterating the request list.

        Args:
            tmdb_ids: TMDB tv ids to look up.
            allowed_library_ids: Optional per-profile ACL filter. When
                non-``None``, results are restricted to rows whose
                ``library_id`` is in the supplied set. ``None``
                (default) applies no library filter.

        Returns:
            Dict mapping ``tmdb_id`` to the matching ``Series``. Empty
            when ``tmdb_ids`` is empty or no rows match.
        """
        ...

    @abstractmethod
    async def find_by_episode_id(
        self,
        episode_id: EpisodeId,
        *,
        allowed_library_ids: Sequence[LibraryId] | None = None,
    ) -> Series | None:
        """Find a series containing an episode with this ID.

        Args:
            episode_id: The episode's external ID.
            allowed_library_ids: Optional per-profile ACL filter. When
                non-``None``, the lookup is restricted to series rows
                whose ``library_id`` is in the supplied set. ``None``
                (default) applies no library filter.

        Returns:
            The Series if found, None otherwise.
        """
        ...

    @abstractmethod
    async def find_by_title(
        self,
        title: Title,
        *,
        allowed_library_ids: Sequence[LibraryId] | None = None,
    ) -> Series | None:
        """Find a series by its title (case-insensitive).

        Args:
            title: The series title to search for.
            allowed_library_ids: Optional per-profile ACL filter. When
                non-``None``, the lookup is restricted to rows whose
                ``library_id`` is in the supplied set. ``None``
                (default) applies no library filter.

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

    @abstractmethod
    async def find_episode_by_id(self, episode_id: EpisodeId) -> Episode | None:
        """Return a single episode by external id, detached from its series.

        Used by orchestration code (eager scrub-preview generation, manual
        intro/credits edits) that needs to act on one episode without
        loading its parent ``Series`` and all sibling episodes.

        Args:
            episode_id: External id of the episode (epi_xxx).

        Returns:
            The detached ``Episode`` if it exists and is not soft-deleted,
            otherwise ``None``.
        """
        ...

    @abstractmethod
    async def episode_file_size_by_library(self) -> dict[str, int]:
        """Return ``{library_id: total episode primary-file bytes}``."""
        ...

    @abstractmethod
    async def count_under_paths(self, paths: Sequence[str]) -> int:
        """Count distinct series with at least one episode under ``paths``.

        The "series belongs to library X" relationship is implicit
        through its episode file paths. A series that happens to
        straddle two libraries counts once per library it touches.

        Args:
            paths: Absolute directory paths to include. Matching is a
                string-prefix + separator check that handles both
                backslash and forward-slash styles.

        Returns:
            Distinct count of series meeting the condition. ``0`` for
            an empty list.
        """
        ...

    @abstractmethod
    async def count(self) -> int:
        """Return the total number of non-deleted series.

        Drives the admin Overview stat card.
        """
        ...


class SeriesRepository(
    SeriesCatalogRepository,
    SeriesScrubPreviewRepository,
    SeriesArtworkMirrorRepository,
    SeriesIntroDetectionRepository,
    SeriesCreditsDetectionRepository,
):
    """Composite Series repository — the full port over the series tables.

    Unions the lean catalog with every job-oriented role-interface
    (ADR-033). This is the type the ``MediaUnitOfWork`` exposes as
    ``.series`` and the SQLAlchemy adapter implements; a consumer that
    only needs one concern should depend on the narrow role instead.
    """


__all__ = ["SeriesCatalogRepository", "SeriesRepository"]
