"""Series repository interface."""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from datetime import datetime

from src.building_blocks.domain.pagination import PaginatedResult
from src.modules.media.domain.entities.episode import Episode
from src.modules.media.domain.entities.season import Season
from src.modules.media.domain.entities.series import Series
from src.modules.media.domain.repositories.movie_repository import (
    CreditsStatusRow,
    GenreRow,
    RemoteArtworkRow,
)
from src.modules.media.domain.value_objects import (
    CreditsDetectionState,
    CreditsMarker,
    EpisodeId,
    FilePath,
    Genre,
    IntroDetectionState,
    IntroMarker,
    SeasonId,
    SeriesId,
    Title,
)
from src.shared_kernel.value_objects.library_id import LibraryId


class SeriesRepository(ABC):
    """Repository interface for Series aggregate.

    This is a port in the hexagonal architecture pattern.
    Implementations (adapters) will be in the infrastructure layer.
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
        ``MovieRepository.list_recently_added``. The home-page
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
        *,
        lang: str = "en",
        allowed_library_ids: Sequence[LibraryId] | None = None,
    ) -> PaginatedResult[Series]:
        """List series belonging to a specific genre, paginated.

        Sorted by ``(LOWER(COALESCE(localized[lang].title, title)) ASC,
        id ASC)``. Same contract as
        ``MovieRepository.list_paginated_by_genre`` — see that method
        for the full description of the cursor format and the genre
        filter (whole-word LIKE on the comma-separated ``genres``
        column).
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

        Same contract as ``MovieRepository.search`` — returns
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
    ) -> Sequence[Series]:
        """Return random series, optionally filtering to those with backdrop.

        Args:
            limit: Maximum number of series to return.
            with_backdrop: If True, only return series with a backdrop_path.
            allowed_library_ids: Optional per-profile ACL filter. When
                non-``None``, results are restricted to rows whose
                ``library_id`` is in the supplied set. ``None``
                (default) applies no library filter.

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

        Used by orchestration code (eager scrub-preview generation) that
        needs to act on one episode without loading its parent ``Series``
        and all sibling episodes.

        Args:
            episode_id: External id of the episode (epi_xxx).

        Returns:
            The detached ``Episode`` if it exists and is not soft-deleted,
            otherwise ``None``.
        """
        ...

    @abstractmethod
    async def find_episodes_missing_scrub_preview(self, limit: int) -> Sequence[Episode]:
        """Return up to ``limit`` episodes that have no scrub-preview thumbnails yet.

        Returned ``Episode`` aggregates are detached from their parent
        ``Series``; the backfill job only needs the file path and id to
        do its work and this avoids loading a full series hierarchy per
        episode. Soft-deleted episodes are excluded.

        Args:
            limit: Maximum number of episodes to return.

        Returns:
            Sequence of episodes whose ``scrub_preview_path`` is null.
        """
        ...

    @abstractmethod
    async def update_episode_scrub_preview_path(
        self,
        episode_id: EpisodeId,
        path: str | None,
    ) -> bool:
        """Persist the scrub-preview path for a single episode.

        Provided alongside ``find_episodes_missing_scrub_preview`` so
        the backfill job can mark items processed without round-tripping
        the entire ``Series`` aggregate — that round-trip would dominate
        runtime on series with many episodes.

        Args:
            episode_id: External id of the episode to update.
            path: Absolute path to the sprite VTT, or ``None`` to clear.

        Returns:
            ``True`` if a row was updated, ``False`` if no episode with
            that id exists.
        """
        ...

    @abstractmethod
    async def find_with_remote_artwork(self, limit: int) -> Sequence[RemoteArtworkRow]:
        """Return up to ``limit`` series with a still-remote artwork URL.

        Mirror of ``MovieRepository.find_with_remote_artwork`` over
        series ``poster_path`` / ``backdrop_path`` / ``logo_path``. Season
        posters and episode stills are handled separately (ADR-029 PR 3).
        """
        ...

    @abstractmethod
    async def update_series_artwork(
        self,
        series_id: SeriesId,
        *,
        poster_path: str | None,
        backdrop_path: str | None,
        logo_path: str | None,
    ) -> None:
        """Set the three artwork columns for one series by external id.

        A targeted column update rather than an aggregate ``save`` so the
        mirror job never risks persisting the series with its seasons and
        episodes unloaded. Callers pass the final value for every column.
        """
        ...

    @abstractmethod
    async def find_seasons_pending_intro_detection(
        self,
        limit: int,
        *,
        stale_before: datetime,
    ) -> Sequence[Season]:
        """Return seasons whose intro-detection job has not converged yet.

        A season is eligible when it is:

        * ``NOT_STARTED`` — never attempted; or
        * ``INSUFFICIENT_EPISODES`` *and* its current (non-deleted)
          episode count exceeds ``intro_detection_attempted_episode_count``
          — i.e. new episodes landed since the last attempt, so the
          outcome could now differ. A season whose episode set hasn't
          grown is NOT retried, so a permanently-small season (e.g. a
          2-part miniseries) stops monopolising the queue; or
        * ``IN_PROGRESS`` with ``intro_detection_attempted_at`` older than
          ``stale_before`` — an orphaned claim (the worker died
          mid-detection), reclaimed so it self-heals.

        ``COMPLETED``, ``FAILED``, and ``DISABLED`` are excluded;
        ``FAILED`` and ``DISABLED`` require an explicit operator reset.

        Ordered by ``intro_detection_attempted_at`` ascending with NULLs
        first, then ``id``, so never-attempted seasons run before any
        already-attempted one.

        Returned ``Season`` entities have their ``episodes`` collection
        eagerly loaded (with file variants) so the detection job can
        iterate file paths without N+1 queries. Soft-deleted seasons
        and episodes are filtered out.

        Args:
            limit: Maximum number of seasons to return.
            stale_before: Cutoff for reclaiming orphaned ``IN_PROGRESS``
                seasons — those last attempted before this instant are
                considered abandoned and made eligible again.

        Returns:
            Sequence of seasons eligible for the next detection tick.
        """
        ...

    @abstractmethod
    async def update_season_intro_detection(
        self,
        season_id: SeasonId,
        state: IntroDetectionState,
        *,
        attempted_at: datetime | None = None,
        attempted_episode_count: int | None = None,
        error: str | None = None,
    ) -> bool:
        """Persist intro-detection job state for a season.

        Direct UPDATE on the ``seasons`` table — analogous to
        ``update_episode_scrub_preview_path`` — so the detection job can
        record progress and outcomes without round-tripping the parent
        ``Series`` aggregate per season. Domain-side state machine
        validation belongs on the ``Season`` entity; callers are expected
        to drive transitions via ``with_detection_started`` etc. and pass
        the resulting state here.

        Args:
            season_id: External id of the season (sea_xxx).
            state: New ``IntroDetectionState`` value.
            attempted_at: When the job ran. Pass ``None`` to leave the
                column unchanged for transient transitions like
                ``IN_PROGRESS``.
            attempted_episode_count: Episode count observed this attempt,
                used to decide whether an ``INSUFFICIENT_EPISODES`` season
                is worth retrying later. Pass ``None`` to leave it
                unchanged (e.g. on the ``IN_PROGRESS`` claim).
            error: Diagnostic message for ``FAILED`` runs, or ``None`` to
                clear.

        Returns:
            ``True`` if a row was updated, ``False`` if no season with
            that id exists.
        """
        ...

    @abstractmethod
    async def update_episode_intro(
        self,
        episode_id: EpisodeId,
        marker: IntroMarker | None,
    ) -> bool:
        """Persist (or clear) the intro marker for a single episode.

        Direct UPDATE on the ``episodes`` table covering all five intro
        columns at once. The detection job calls this per-episode after
        cross-correlation; the manual-edit endpoint also uses it to set
        a ``MANUAL`` marker without rewriting the entire ``Series``
        aggregate.

        Args:
            episode_id: External id of the episode (epi_xxx).
            marker: The marker to persist, or ``None`` to clear all five
                intro columns.

        Returns:
            ``True`` if a row was updated, ``False`` if no episode with
            that id exists.
        """
        ...

    @abstractmethod
    async def clear_auto_intro_markers_for_season(self, season_id: SeasonId) -> int:
        """Clear AUTO_DETECTED intro markers on a season's episodes.

        Bulk UPDATE that nulls the five intro columns for every episode
        of the season whose marker source is ``AUTO_DETECTED``. MANUAL
        markers are left untouched. Used by the re-detect flow so a
        re-run starts from a clean slate without dropping operator edits.

        Args:
            season_id: External id of the season (ssn_xxx).

        Returns:
            The number of episode rows cleared.
        """
        ...

    @abstractmethod
    async def count_episode_credits_states(self) -> dict[str, int]:
        """Return ``{credits_detection_state: count}`` over non-deleted episodes."""
        ...

    @abstractmethod
    async def episode_file_size_by_library(self) -> dict[str, int]:
        """Return ``{library_id: total episode primary-file bytes}``."""
        ...

    @abstractmethod
    async def list_episode_credits_status(
        self, state: str | None, limit: int, offset: int
    ) -> tuple[Sequence[CreditsStatusRow], int]:
        """Return a page of episode credits-status rows + the total count.

        Rows carry ``series_id``/``season_number``/``episode_number`` so the
        admin UI can deep-link into the per-episode editor. Newest-marker
        first, then by series + season + episode.
        """
        ...

    @abstractmethod
    async def find_episodes_pending_credits_detection(self, limit: int) -> Sequence[Episode]:
        """Return episodes whose credits detection has not run yet.

        Filters for episodes in ``NOT_STARTED`` credits-detection state
        (per-file, unlike the season-scoped intro detection), with their
        file variants eager-loaded so the job can read the primary file
        path without an N+1. Soft-deleted episodes are excluded.

        Args:
            limit: Maximum number of episodes to return.

        Returns:
            Sequence of episodes eligible for the next credits tick.
        """
        ...

    @abstractmethod
    async def update_episode_credits(
        self,
        episode_id: EpisodeId,
        marker: CreditsMarker | None,
        state: CreditsDetectionState,
    ) -> bool:
        """Persist the credits marker + detection state for one episode.

        Direct UPDATE of the four credits-marker columns plus
        ``credits_detection_state`` on the ``episodes`` row, avoiding a
        round-trip through the ``Series`` aggregate. ``marker=None`` clears
        the marker columns (used for IN_PROGRESS / NO_CREDITS_FOUND /
        FAILED transitions and for clearing); a non-null marker writes the
        onset (used on COMPLETED and manual edits).

        Args:
            episode_id: External id of the episode (epi_xxx).
            marker: The marker to persist, or ``None`` to clear it.
            state: New ``CreditsDetectionState`` value.

        Returns:
            ``True`` if a row was updated, ``False`` if no episode matched.
        """
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


__all__ = ["SeriesRepository"]
