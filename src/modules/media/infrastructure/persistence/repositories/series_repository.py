"""SQLAlchemy implementation of SeriesRepository."""

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import and_, distinct, func, or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.building_blocks.application.pagination import (
    PaginatedResult,
    Pagination,
    decode_cursor,
    encode_cursor,
)
from src.modules.media.domain.entities import Episode, Season, Series
from src.modules.media.domain.repositories import SeriesRepository
from src.modules.media.domain.repositories.movie_repository import CreditsStatusRow, GenreRow
from src.modules.media.domain.value_objects import (
    CreditsDetectionState,
    CreditsMarker,
    EpisodeId,
    FilePath,
    Genre,
    IntroDetectionState,
    IntroMarker,
    IntroMarkerSource,
    SeasonId,
    SeriesId,
    Title,
)
from src.modules.media.infrastructure.persistence.mappers import (
    EpisodeMapper,
    SeasonMapper,
    SeriesMapper,
)
from src.modules.media.infrastructure.persistence.models import (
    EpisodeModel,
    MediaFileModel,
    SeasonModel,
    SeriesModel,
)
from src.modules.media.infrastructure.persistence.repositories._genre_helpers import (
    fetch_genre_paginated_page,
    fetch_genre_rows,
)
from src.modules.media.infrastructure.persistence.repositories._path_prefix_helpers import (
    build_path_prefix_filters,
)
from src.shared_kernel.value_objects.library_id import LibraryId


def _series_filter_conditions(
    *,
    allowed_library_ids: Sequence[LibraryId] | None,
    library_id: str | None,
    has_tmdb_id: bool | None,
    fts_matching_ids: Sequence[int] | None,
) -> list:
    """Build SQLAlchemy ``WHERE`` clauses for the optional series filters.

    Mirrors ``_movie_filter_conditions`` so both repositories surface
    the same admin-facing filter contract. ``fts_matching_ids`` is
    the result of pre-querying ``series_fts`` for the operator's
    ``q`` text; the caller resolves it once before the page query.
    """
    conditions: list = []
    if allowed_library_ids is not None:
        conditions.append(
            SeriesModel.library_id.in_([library_id.value for library_id in allowed_library_ids])
        )
    if library_id is not None:
        conditions.append(SeriesModel.library_id == library_id)
    if has_tmdb_id is not None:
        conditions.append(
            SeriesModel.tmdb_id.is_not(None) if has_tmdb_id else SeriesModel.tmdb_id.is_(None),
        )
    if fts_matching_ids is not None:
        conditions.append(SeriesModel.id.in_(fts_matching_ids))
    return conditions


async def _series_fts_matching_ids(session: AsyncSession, query: str) -> list[int]:
    """Resolve ``query`` against ``series_fts`` and return matching ids.

    Mirrors ``_movie_fts_matching_ids`` — same FTS5 column surface
    minus the movie-specific ``tagline`` / ``writers`` /
    ``collection_name`` / ``directors`` projections (series don't
    carry those fields).

    Returns ``[]`` when the sanitized query is empty or has no
    matches; caller short-circuits with an empty page.
    """
    from src.modules.media.infrastructure.persistence.repositories.movie_repository import (
        _prepare_fts_query,
    )

    fts_query = _prepare_fts_query(query)
    if not fts_query:
        return []
    sql = """
        SELECT rowid FROM series_fts
        WHERE series_fts MATCH :query
    """
    result = await session.execute(text(sql), {"query": fts_query})
    return [row[0] for row in result.fetchall()]


class SQLAlchemySeriesRepository(SeriesRepository):
    """SQLAlchemy implementation of SeriesRepository.

    Provides async database operations for Series aggregates,
    including nested seasons and episodes.

    Example:
        >>> repo = SQLAlchemySeriesRepository(session)
        >>> series = await repo.find_by_id(SeriesId("ser_abc123"))
    """

    def __init__(self, session: AsyncSession) -> None:
        """Initialize repository with database session.

        Args:
            session: SQLAlchemy async session.
        """
        self._session = session

    @staticmethod
    def _series_load_options() -> list[Any]:
        """Return common eager-loading options for series queries."""
        return [
            selectinload(SeriesModel.seasons)
            .selectinload(SeasonModel.episodes)
            .selectinload(EpisodeModel.file_variants),
        ]

    async def find_by_id(
        self,
        series_id: SeriesId,
        *,
        allowed_library_ids: Sequence[LibraryId] | None = None,
    ) -> Series | None:
        """Find a series by its ID (includes seasons and episodes).

        Args:
            series_id: The series' external ID.
            allowed_library_ids: Optional per-profile ACL filter.

        Returns:
            The Series if found, None otherwise.
        """
        stmt = (
            select(SeriesModel)
            .where(
                SeriesModel.external_id == str(series_id),
                SeriesModel.deleted_at.is_(None),
            )
            .options(*self._series_load_options())
            .execution_options(populate_existing=True)
        )
        if allowed_library_ids is not None:
            stmt = stmt.where(
                SeriesModel.library_id.in_([library_id.value for library_id in allowed_library_ids])
            )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()

        return None if model is None else SeriesMapper.to_entity(model)

    async def find_needs_enrichment_review(
        self,
        *,
        allowed_library_ids: Sequence[LibraryId] | None = None,
    ) -> Sequence[Series]:
        """Return series with the review flag set, newest-first."""
        conditions = [
            SeriesModel.deleted_at.is_(None),
            SeriesModel.needs_enrichment_review.is_(True),
        ]
        if allowed_library_ids is not None:
            allowed = [library_id.value for library_id in allowed_library_ids]
            if not allowed:
                return []
            conditions.append(SeriesModel.library_id.in_(allowed))

        stmt = (
            select(SeriesModel)
            .where(*conditions)
            .options(*self._series_load_options())
            .order_by(SeriesModel.updated_at.desc())
        )
        result = await self._session.execute(stmt)
        return [SeriesMapper.to_entity(model) for model in result.scalars().all()]

    async def save(self, series: Series) -> Series:
        """Persist a series with all its seasons and episodes.

        Args:
            series: The series to save.

        Returns:
            The saved series (with generated IDs if new).
        """
        # Generate IDs for entities that don't have them
        series = self._ensure_ids(series)

        # Check if series already exists (load seasons for update)
        stmt = (
            select(SeriesModel)
            .where(SeriesModel.external_id == str(series.id))
            .options(*self._series_load_options())
            .execution_options(populate_existing=True)
        )
        result = await self._session.execute(stmt)
        existing_model = result.scalar_one_or_none()

        if existing_model is not None:
            # Restore if soft-deleted (including children)
            if existing_model.is_deleted:
                existing_model.restore()
                for season in existing_model.seasons:
                    season.restore()
                    for episode in season.episodes:
                        episode.restore()

            return await self._update_series(existing_model, series)

        return await self._create_series(series)

    async def delete(self, series_id: SeriesId) -> bool:
        """Soft delete a series and all its seasons/episodes.

        Args:
            series_id: The series' external ID.

        Returns:
            True if deleted, False if not found.
        """
        stmt = (
            select(SeriesModel)
            .where(
                SeriesModel.external_id == str(series_id),
                SeriesModel.deleted_at.is_(None),
            )
            .options(
                selectinload(SeriesModel.seasons).selectinload(SeasonModel.episodes),
            )
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()

        if model is None:
            return False

        # Soft delete series and all children
        model.soft_delete()
        for season in model.seasons:
            season.soft_delete()
            for episode in season.episodes:
                episode.soft_delete()

        await self._session.flush()
        return True

    async def list_all(self) -> Sequence[Series]:
        """List all series (excluding soft-deleted, includes seasons and episodes).

        Returns:
            Sequence of all series ordered by title.
        """
        stmt = (
            select(SeriesModel)
            .where(SeriesModel.deleted_at.is_(None))
            .options(*self._series_load_options())
            .order_by(SeriesModel.title)
        )
        result = await self._session.execute(stmt)
        models = result.scalars().all()

        return [SeriesMapper.to_entity(model) for model in models]

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
        """List series in a single cursor-paginated page.

        Sorted by ``id DESC`` so the most recently inserted rows appear
        first — see the building-block docstring and the matching
        ``MovieRepository.list_paginated`` for the full justification.
        Soft-deleted rows are filtered out the same way as ``list_all``.
        Fetches ``limit + 1`` rows to detect ``has_more`` cheaply
        without an extra query. The full season / episode hierarchy is
        loaded via the same options as ``list_all``; if that turns out
        to be a perf issue we'll add a shallow variant later.

        Admin filters (``library_id``, ``has_tmdb_id``) compose with
        the per-profile ``allowed_library_ids`` ACL — see the matching
        helper on the movie repository for the contract.

        ``q`` is delegated to the ``series_fts`` virtual table for
        i18n-aware matching across title / original_title / synopsis
        / genres / cast plus every ``localized_*`` projection. The
        FTS5 ``MATCH`` resolves to a set of internal ids that is
        then composed as ``id IN (...)`` so cursor pagination stays
        ordered by ``id DESC`` (consistent page-by-page admin walk)
        rather than relevance.
        """
        fts_matching_ids: list[int] | None = None
        if q and q.strip():
            fts_matching_ids = await _series_fts_matching_ids(self._session, q)
            if not fts_matching_ids:
                return PaginatedResult(
                    items=[],
                    pagination=Pagination(next_cursor=None, has_more=False),
                    total_count=0 if include_total else None,
                )

        conditions = _series_filter_conditions(
            allowed_library_ids=allowed_library_ids,
            library_id=library_id,
            has_tmdb_id=has_tmdb_id,
            fts_matching_ids=fts_matching_ids,
        )

        decoded = decode_cursor(cursor)

        stmt = (
            select(SeriesModel)
            .where(SeriesModel.deleted_at.is_(None), *conditions)
            .options(*self._series_load_options())
        )

        if decoded is not None:
            stmt = stmt.where(SeriesModel.id < decoded.id)

        stmt = stmt.order_by(SeriesModel.id.desc()).limit(limit + 1)

        result = await self._session.execute(stmt)
        models = list(result.scalars().all())

        has_more = len(models) > limit
        if has_more:
            models = models[:limit]

        next_cursor: str | None = None
        if has_more and models:
            next_cursor = encode_cursor(models[-1].id)

        total_count: int | None = None
        if include_total:
            count_stmt = (
                select(func.count())
                .select_from(SeriesModel)
                .where(SeriesModel.deleted_at.is_(None), *conditions)
            )
            total_count = (await self._session.execute(count_stmt)).scalar_one()

        return PaginatedResult(
            items=[SeriesMapper.to_entity(m) for m in models],
            pagination=Pagination(next_cursor=next_cursor, has_more=has_more),
            total_count=total_count,
        )

    async def list_recently_added(
        self,
        limit: int,
        *,
        allowed_library_ids: Sequence[LibraryId] | None = None,
    ) -> Sequence[Series]:
        """Return the top ``limit`` non-deleted series, newest first.

        Same ``id DESC`` ordering as ``list_paginated`` — see the
        matching ``MovieRepository.list_recently_added`` for the full
        justification. The series hierarchy (seasons/episodes/file
        variants) is eager-loaded via the same options as ``list_all``
        so callers don't N+1 when rendering the carousel.
        """
        stmt = (
            select(SeriesModel)
            .where(SeriesModel.deleted_at.is_(None))
            .options(*self._series_load_options())
        )
        if allowed_library_ids is not None:
            stmt = stmt.where(
                SeriesModel.library_id.in_([library_id.value for library_id in allowed_library_ids])
            )
        stmt = stmt.order_by(SeriesModel.id.desc()).limit(limit)
        result = await self._session.execute(stmt)
        return [SeriesMapper.to_entity(m) for m in result.scalars().all()]

    async def list_genre_rows(
        self,
        lang: str,
        *,
        allowed_library_ids: Sequence[LibraryId] | None = None,
    ) -> Sequence[GenreRow]:
        """Project the genre columns of every non-deleted series row."""
        return await fetch_genre_rows(
            self._session,
            SeriesModel,
            lang,
            allowed_library_ids=allowed_library_ids,
        )

    async def list_paginated_by_genre(
        self,
        genre: Genre,
        cursor: str | None,
        limit: int,
        *,
        allowed_library_ids: Sequence[LibraryId] | None = None,
    ) -> PaginatedResult[Series]:
        """List series for a single genre, paginated and sorted by title.

        Delegates the SQL boilerplate to the shared
        ``fetch_genre_paginated_page`` helper so this method and its
        movie counterpart stay in lockstep. The full season / episode
        hierarchy is loaded via the existing ``_series_load_options``
        because consumers may want to render episode counts on the
        carousel card.
        """
        return await fetch_genre_paginated_page(
            session=self._session,
            model=SeriesModel,
            mapper_to_entity=SeriesMapper.to_entity,
            options=list(self._series_load_options()),
            genre=genre,
            cursor=cursor,
            limit=limit,
            allowed_library_ids=allowed_library_ids,
        )

    async def find_random(
        self,
        limit: int,
        *,
        with_backdrop: bool = False,
        allowed_library_ids: Sequence[LibraryId] | None = None,
    ) -> Sequence[Series]:
        """Return random series."""
        from sqlalchemy.sql.expression import func

        stmt = (
            select(SeriesModel)
            .where(SeriesModel.deleted_at.is_(None))
            .options(*self._series_load_options())
        )
        if with_backdrop:
            stmt = stmt.where(
                SeriesModel.backdrop_path.is_not(None),
                SeriesModel.backdrop_path != "",
            )
        if allowed_library_ids is not None:
            stmt = stmt.where(
                SeriesModel.library_id.in_([library_id.value for library_id in allowed_library_ids])
            )
        stmt = stmt.order_by(func.random()).limit(limit)
        result = await self._session.execute(stmt)
        return [SeriesMapper.to_entity(m) for m in result.scalars().all()]

    async def find_by_title(
        self,
        title: Title,
        *,
        allowed_library_ids: Sequence[LibraryId] | None = None,
    ) -> Series | None:
        """Find a series by its title (case-insensitive).

        Args:
            title: The series title to search for.
            allowed_library_ids: Optional per-profile ACL filter.

        Returns:
            The Series if found, None otherwise.
        """
        stmt = (
            select(SeriesModel)
            .where(
                SeriesModel.title.ilike(title.value),
                SeriesModel.deleted_at.is_(None),
            )
            .options(*self._series_load_options())
            .execution_options(populate_existing=True)
        )
        if allowed_library_ids is not None:
            stmt = stmt.where(
                SeriesModel.library_id.in_([library_id.value for library_id in allowed_library_ids])
            )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()

        return None if model is None else SeriesMapper.to_entity(model)

    async def find_by_ids(
        self,
        series_ids: Sequence[SeriesId],
        *,
        allowed_library_ids: Sequence[LibraryId] | None = None,
    ) -> dict[str, Series]:
        """Find multiple series by their IDs in a single query."""
        if not series_ids:
            return {}

        ext_ids = [str(sid) for sid in series_ids]
        stmt = (
            select(SeriesModel)
            .where(
                SeriesModel.external_id.in_(ext_ids),
                SeriesModel.deleted_at.is_(None),
            )
            .options(*self._series_load_options())
            .execution_options(populate_existing=True)
        )
        if allowed_library_ids is not None:
            stmt = stmt.where(
                SeriesModel.library_id.in_([library_id.value for library_id in allowed_library_ids])
            )
        result = await self._session.execute(stmt)
        return {
            model.external_id: SeriesMapper.to_entity(model) for model in result.scalars().all()
        }

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
        """
        if not tmdb_ids:
            return {}
        stmt = (
            select(SeriesModel)
            .where(
                SeriesModel.tmdb_id.in_(tmdb_ids),
                SeriesModel.deleted_at.is_(None),
            )
            .options(*self._series_load_options())
            .execution_options(populate_existing=True)
        )
        if allowed_library_ids is not None:
            stmt = stmt.where(
                SeriesModel.library_id.in_([library_id.value for library_id in allowed_library_ids])
            )
        result = await self._session.execute(stmt)
        return {
            model.tmdb_id: SeriesMapper.to_entity(model)
            for model in result.scalars().all()
            if model.tmdb_id is not None
        }

    async def find_by_episode_id(
        self,
        episode_id: EpisodeId,
        *,
        allowed_library_ids: Sequence[LibraryId] | None = None,
    ) -> Series | None:
        """Find a series containing an episode with this ID.

        Args:
            episode_id: The episode's external ID.
            allowed_library_ids: Optional per-profile ACL filter
                forwarded to the inner ``find_by_id`` lookup.

        Returns:
            The Series if found, None otherwise.
        """
        stmt = select(EpisodeModel).where(
            EpisodeModel.external_id == str(episode_id),
            EpisodeModel.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        episode_model = result.scalar_one_or_none()

        if episode_model is None:
            return None

        return await self.find_by_id(
            SeriesId(episode_model.series_external_id),
            allowed_library_ids=allowed_library_ids,
        )

    async def find_by_file_path(self, file_path: FilePath) -> Series | None:
        """Find a series containing an episode with this file path.

        Searches both the file_variants table and the flat column
        for backward compatibility.

        Args:
            file_path: The absolute file path.

        Returns:
            The Series if found, None otherwise.
        """
        # Search in file_variants table
        stmt = (
            select(EpisodeModel)
            .join(MediaFileModel, MediaFileModel.episode_id == EpisodeModel.id)
            .where(
                MediaFileModel.file_path == str(file_path),
                EpisodeModel.deleted_at.is_(None),
            )
        )
        result = await self._session.execute(stmt)
        episode_model = result.scalar_one_or_none()

        if episode_model is None:
            # Fallback to flat column
            stmt = select(EpisodeModel).where(
                EpisodeModel.file_path == str(file_path),
                EpisodeModel.deleted_at.is_(None),
            )
            result = await self._session.execute(stmt)
            episode_model = result.scalar_one_or_none()

        if episode_model is None:
            return None

        # Load the full series
        return await self.find_by_id(SeriesId(episode_model.series_external_id))

    async def find_episode_by_id(self, episode_id: EpisodeId) -> Episode | None:
        """Return a single episode by external id, detached from its series."""
        stmt = (
            select(EpisodeModel)
            .where(
                EpisodeModel.external_id == str(episode_id),
                EpisodeModel.deleted_at.is_(None),
            )
            .options(selectinload(EpisodeModel.file_variants))
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return None if model is None else EpisodeMapper.to_entity(model)

    async def find_episodes_missing_scrub_preview(self, limit: int) -> Sequence[Episode]:
        """Return up to ``limit`` episodes whose ``scrub_preview_path`` is null.

        Returns detached ``Episode`` entities (no parent ``Series``
        loaded) — the backfill job only needs the file path and id.
        ``file_variants`` is eager-loaded so the resulting entity
        exposes ``primary_file.file_path`` without a lazy round-trip.
        """
        stmt = (
            select(EpisodeModel)
            .where(
                EpisodeModel.deleted_at.is_(None),
                EpisodeModel.scrub_preview_path.is_(None),
            )
            .options(selectinload(EpisodeModel.file_variants))
            .order_by(EpisodeModel.id.asc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return [EpisodeMapper.to_entity(model) for model in result.scalars().all()]

    async def update_episode_scrub_preview_path(
        self,
        episode_id: EpisodeId,
        path: str | None,
    ) -> bool:
        """Update only the ``scrub_preview_path`` column of an episode row.

        Direct UPDATE on the episodes table — far cheaper than loading
        the full ``Series`` aggregate just to mutate one column on one
        child. Soft-deleted rows are excluded so a backfill job that
        races a delete cannot resurrect a tombstoned episode.
        """
        stmt = (
            update(EpisodeModel)
            .where(
                EpisodeModel.external_id == str(episode_id),
                EpisodeModel.deleted_at.is_(None),
            )
            .values(scrub_preview_path=path)
        )
        result = await self._session.execute(stmt)
        return bool(result.rowcount)

    async def find_seasons_pending_intro_detection(
        self,
        limit: int,
        *,
        stale_before: datetime,
    ) -> Sequence[Season]:
        """Return seasons eligible for the next intro-detection tick.

        Episodes (and their file_variants) are eager-loaded so the
        detection job can iterate file paths without N+1 queries.
        Soft-deleted rows are filtered out at both levels.

        Eligibility (see the interface for the rationale):

        * ``NOT_STARTED`` — never attempted.
        * ``INSUFFICIENT_EPISODES`` whose live episode count now exceeds
          ``intro_detection_attempted_episode_count`` (NULL counts as 0,
          so legacy rows get exactly one more pass before the count is
          stamped). A season whose episode set hasn't grown is skipped,
          so a permanently-small season stops monopolising the queue.
        * ``IN_PROGRESS`` last touched before ``stale_before`` — an
          orphaned claim, reclaimed so a crash/restart self-heals.

        Ordered by ``intro_detection_attempted_at`` ascending with NULLs
        first, then ``id``: a never-attempted season (NULL) always runs
        before any already-attempted one. ``nullsfirst`` is explicit
        because SQLite (NULLs first on ASC) and PostgreSQL (NULLs last)
        disagree on the default.
        """
        live_episode_count = (
            select(func.count(EpisodeModel.id))
            .where(
                EpisodeModel.season_id == SeasonModel.id,
                EpisodeModel.deleted_at.is_(None),
            )
            .correlate(SeasonModel)
            .scalar_subquery()
        )
        stmt = (
            select(SeasonModel)
            .where(
                SeasonModel.deleted_at.is_(None),
                or_(
                    SeasonModel.intro_detection_state == IntroDetectionState.NOT_STARTED.value,
                    and_(
                        SeasonModel.intro_detection_state
                        == IntroDetectionState.INSUFFICIENT_EPISODES.value,
                        live_episode_count
                        > func.coalesce(SeasonModel.intro_detection_attempted_episode_count, 0),
                    ),
                    and_(
                        SeasonModel.intro_detection_state == IntroDetectionState.IN_PROGRESS.value,
                        SeasonModel.intro_detection_attempted_at.is_not(None),
                        SeasonModel.intro_detection_attempted_at < stale_before,
                    ),
                ),
            )
            .options(selectinload(SeasonModel.episodes).selectinload(EpisodeModel.file_variants))
            .order_by(
                SeasonModel.intro_detection_attempted_at.asc().nullsfirst(),
                SeasonModel.id.asc(),
            )
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return [SeasonMapper.to_entity(model) for model in result.scalars().all()]

    async def update_season_intro_detection(
        self,
        season_id: SeasonId,
        state: IntroDetectionState,
        *,
        attempted_at: datetime | None = None,
        attempted_episode_count: int | None = None,
        error: str | None = None,
    ) -> bool:
        """Direct UPDATE of intro-detection columns on the seasons row.

        ``attempted_at`` and ``attempted_episode_count`` are left
        untouched when ``None`` so transient transitions (e.g. claiming a
        season as IN_PROGRESS) do not overwrite the values from the
        previous terminal run. ``error`` is always written through —
        pass ``None`` to clear.
        """
        values: dict[str, Any] = {
            "intro_detection_state": state.value,
            "intro_detection_error": error,
        }
        if attempted_at is not None:
            values["intro_detection_attempted_at"] = attempted_at
        if attempted_episode_count is not None:
            values["intro_detection_attempted_episode_count"] = attempted_episode_count

        stmt = (
            update(SeasonModel)
            .where(
                SeasonModel.external_id == str(season_id),
                SeasonModel.deleted_at.is_(None),
            )
            .values(**values)
        )
        result = await self._session.execute(stmt)
        return bool(result.rowcount)

    async def update_episode_intro(
        self,
        episode_id: EpisodeId,
        marker: IntroMarker | None,
    ) -> bool:
        """Direct UPDATE of the 5 intro columns on the episodes row.

        Used by the auto-detection job and the manual-edit endpoint to
        avoid round-tripping the parent ``Series`` aggregate. Passing
        ``None`` clears all five columns atomically.
        """
        if marker is None:
            values: dict[str, Any] = {
                "intro_start_seconds": None,
                "intro_end_seconds": None,
                "intro_source": None,
                "intro_confidence": None,
                "intro_detected_at": None,
            }
        else:
            values = {
                "intro_start_seconds": marker.start_seconds,
                "intro_end_seconds": marker.end_seconds,
                "intro_source": marker.source.value,
                "intro_confidence": marker.confidence,
                "intro_detected_at": marker.detected_at,
            }

        stmt = (
            update(EpisodeModel)
            .where(
                EpisodeModel.external_id == str(episode_id),
                EpisodeModel.deleted_at.is_(None),
            )
            .values(**values)
        )
        result = await self._session.execute(stmt)
        return bool(result.rowcount)

    async def clear_auto_intro_markers_for_season(self, season_id: SeasonId) -> int:
        """Null the intro columns of a season's AUTO_DETECTED episodes."""
        season_pk = select(SeasonModel.id).where(
            SeasonModel.external_id == str(season_id),
            SeasonModel.deleted_at.is_(None),
        )
        stmt = (
            update(EpisodeModel)
            .where(
                EpisodeModel.season_id.in_(season_pk),
                EpisodeModel.intro_source == IntroMarkerSource.AUTO_DETECTED.value,
                EpisodeModel.deleted_at.is_(None),
            )
            .values(
                intro_start_seconds=None,
                intro_end_seconds=None,
                intro_source=None,
                intro_confidence=None,
                intro_detected_at=None,
            )
        )
        result = await self._session.execute(stmt)
        return int(result.rowcount or 0)

    async def count_episode_credits_states(self) -> dict[str, int]:
        """Return ``{credits_detection_state: count}`` over non-deleted episodes."""
        stmt = (
            select(EpisodeModel.credits_detection_state, func.count())
            .where(EpisodeModel.deleted_at.is_(None))
            .group_by(EpisodeModel.credits_detection_state)
        )
        result = await self._session.execute(stmt)
        return dict(result.all())

    async def episode_file_size_by_library(self) -> dict[str, int]:
        """Sum episode primary-file bytes per library, via the parent series."""
        stmt = (
            select(
                SeriesModel.library_id,
                func.coalesce(func.sum(EpisodeModel.file_size), 0),
            )
            .join(SeasonModel, EpisodeModel.season_id == SeasonModel.id)
            .join(SeriesModel, SeasonModel.series_id == SeriesModel.id)
            .where(EpisodeModel.deleted_at.is_(None))
            .group_by(SeriesModel.library_id)
        )
        result = await self._session.execute(stmt)
        return {library_id: int(total) for library_id, total in result.all()}

    async def list_episode_credits_status(
        self, state: str | None, limit: int, offset: int
    ) -> tuple[Sequence[CreditsStatusRow], int]:
        """Return a page of episode credits-status rows + total (newest first)."""
        conditions = [EpisodeModel.deleted_at.is_(None)]
        if state is not None:
            conditions.append(EpisodeModel.credits_detection_state == state)

        total = (
            await self._session.execute(
                select(func.count()).select_from(EpisodeModel).where(*conditions)
            )
        ).scalar_one()

        stmt = (
            select(
                EpisodeModel.external_id,
                EpisodeModel.title,
                EpisodeModel.credits_detection_state,
                EpisodeModel.credits_start_seconds,
                EpisodeModel.credits_source,
                EpisodeModel.credits_confidence,
                EpisodeModel.series_external_id,
                EpisodeModel.season_number,
                EpisodeModel.episode_number,
            )
            .where(*conditions)
            .order_by(
                EpisodeModel.credits_detected_at.desc(),
                EpisodeModel.series_external_id.asc(),
                EpisodeModel.season_number.asc(),
                EpisodeModel.episode_number.asc(),
            )
            .limit(limit)
            .offset(offset)
        )
        rows = (await self._session.execute(stmt)).all()
        items = [
            CreditsStatusRow(
                media_id=r[0],
                title=r[1],
                state=r[2],
                start_seconds=r[3],
                source=r[4],
                confidence=r[5],
                series_id=r[6],
                season_number=r[7],
                episode_number=r[8],
            )
            for r in rows
        ]
        return items, int(total)

    async def find_episodes_pending_credits_detection(self, limit: int) -> Sequence[Episode]:
        """Return NOT_STARTED-credits episodes with file variants loaded."""
        stmt = (
            select(EpisodeModel)
            .where(
                EpisodeModel.deleted_at.is_(None),
                EpisodeModel.credits_detection_state == CreditsDetectionState.NOT_STARTED.value,
            )
            .options(selectinload(EpisodeModel.file_variants))
            .order_by(EpisodeModel.id.asc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return [EpisodeMapper.to_entity(model) for model in result.scalars().all()]

    async def update_episode_credits(
        self,
        episode_id: EpisodeId,
        marker: CreditsMarker | None,
        state: CreditsDetectionState,
    ) -> bool:
        """Direct UPDATE of the 4 credits columns + state on the episodes row."""
        values: dict[str, Any] = {"credits_detection_state": state.value}
        if marker is None:
            values.update(
                credits_start_seconds=None,
                credits_source=None,
                credits_confidence=None,
                credits_detected_at=None,
            )
        else:
            values.update(
                credits_start_seconds=marker.start_seconds,
                credits_source=marker.source.value,
                credits_confidence=marker.confidence,
                credits_detected_at=marker.detected_at,
            )
        stmt = (
            update(EpisodeModel)
            .where(
                EpisodeModel.external_id == str(episode_id),
                EpisodeModel.deleted_at.is_(None),
            )
            .values(**values)
        )
        result = await self._session.execute(stmt)
        return bool(result.rowcount)

    async def count_under_paths(self, paths: Sequence[str]) -> int:
        """Count distinct series with at least one episode under ``paths``.

        One SELECT against ``episodes``, DISTINCT by ``series_id`` so a
        series with ten matching episodes still counts as one. See
        ``_path_prefix_helpers.build_path_prefix_filters`` for the
        normalization rules shared with the movie repo.
        """
        prefix_filters = build_path_prefix_filters(EpisodeModel.file_path, paths)
        if not prefix_filters:
            return 0
        # DISTINCT on series_external_id (not series_id — episodes
        # reference the series via the public external id, not the
        # internal autoincrement pk).
        stmt = select(func.count(distinct(EpisodeModel.series_external_id))).where(
            EpisodeModel.deleted_at.is_(None),
            EpisodeModel.file_path.is_not(None),
            or_(*prefix_filters),
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def count(self) -> int:
        """Return the total number of non-deleted series."""
        stmt = select(func.count()).select_from(SeriesModel).where(SeriesModel.deleted_at.is_(None))
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    def _ensure_ids(self, series: Series) -> Series:
        """Ensure all entities have IDs, generating them if needed.

        Args:
            series: The series to process.

        Returns:
            Series with all IDs populated.
        """
        series_id = SeriesId.generate_if_absent(series.id)

        updated_seasons: list[Season] = []
        for season in series.seasons:
            season_id = SeasonId.generate_if_absent(season.id)

            updated_episodes: list[Episode] = []
            for episode in season.episodes:
                episode_id = EpisodeId.generate_if_absent(episode.id)
                updated_episodes.append(episode.with_updates(id=episode_id, series_id=series_id))

            updated_seasons.append(
                season.with_updates(
                    id=season_id,
                    series_id=series_id,
                    episodes=updated_episodes,
                )
            )

        return series.with_updates(id=series_id, seasons=updated_seasons)

    async def _create_series(self, series: Series) -> Series:
        """Create a new series with all seasons and episodes.

        Args:
            series: The series to create.

        Returns:
            The created series.
        """
        # Create series model
        series_model = SeriesMapper.to_model(series)
        self._session.add(series_model)
        await self._session.flush()

        # Create seasons and episodes
        for season in series.seasons:
            season_model = SeasonMapper.to_model(season, series_model.id)
            self._session.add(season_model)
            await self._session.flush()

            for episode in season.episodes:
                episode_model = EpisodeMapper.to_model(episode, season_model.id)
                self._session.add(episode_model)

        await self._session.flush()

        # Reload and return (series.id is guaranteed to exist after _ensure_ids).
        # Transaction commit is the Unit of Work's responsibility.
        if series.id is None:
            raise RuntimeError("Series id must be assigned before reload")
        result = await self.find_by_id(series.id)
        if result is None:
            raise RuntimeError(f"Series {series.id} disappeared between flush and reload")
        return result

    async def _update_series(
        self,
        existing_model: SeriesModel,
        series: Series,
    ) -> Series:
        """Update existing series with all seasons and episodes.

        Args:
            existing_model: The existing series model.
            series: The series with updated data.

        Returns:
            The updated series.
        """
        # Update series
        SeriesMapper.update_model(existing_model, series)

        # Get existing seasons by external_id
        existing_seasons = {s.external_id: s for s in existing_model.seasons}

        # Update or create seasons
        for season in series.seasons:
            season_ext_id = str(season.id)

            if season_ext_id in existing_seasons:
                season_model = existing_seasons[season_ext_id]
                SeasonMapper.update_model(season_model, season)
                await self._update_season_episodes(season_model, season)
                del existing_seasons[season_ext_id]
            else:
                # New season - add to relationship list
                season_model = SeasonMapper.to_model(season, existing_model.id)
                existing_model.seasons.append(season_model)
                await self._session.flush()

                for episode in season.episodes:
                    episode_model = EpisodeMapper.to_model(episode, season_model.id)
                    self._session.add(episode_model)

        # Soft delete removed seasons and their episodes
        for season_model in existing_seasons.values():
            season_model.soft_delete()
            for ep_model in season_model.episodes:
                ep_model.soft_delete()

        await self._session.flush()

        # Reload and return (series.id is guaranteed to exist).
        # Transaction commit is the Unit of Work's responsibility.
        if series.id is None:
            raise RuntimeError("Series id must be assigned before reload")
        result = await self.find_by_id(series.id)
        if result is None:
            raise RuntimeError(f"Series {series.id} disappeared between flush and reload")
        return result

    async def _update_season_episodes(
        self,
        season_model: SeasonModel,
        season: Season,
    ) -> None:
        """Update episodes for an existing season.

        Args:
            season_model: The existing season model.
            season: The season with updated episodes.
        """
        existing_episodes = {e.external_id: e for e in season_model.episodes}

        for episode in season.episodes:
            episode_ext_id = str(episode.id)

            if episode_ext_id in existing_episodes:
                EpisodeMapper.update_model(existing_episodes[episode_ext_id], episode)
                del existing_episodes[episode_ext_id]
            else:
                # New episode
                episode_model = EpisodeMapper.to_model(episode, season_model.id)
                self._session.add(episode_model)

        # Soft delete removed episodes
        for episode_model in existing_episodes.values():
            episode_model.soft_delete()

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
        """Full-text search using FTS5.

        Same pattern as ``SQLAlchemyMovieRepository.search`` — queries
        ``series_fts``, joins back to ``series``, applies filters.
        """
        from src.modules.media.infrastructure.persistence.repositories.movie_repository import (
            _prepare_fts_query,
        )

        fts_query = _prepare_fts_query(query)
        if not fts_query:
            return []

        sql = """
            SELECT series_fts.rowid, bm25(series_fts) AS rank
            FROM series_fts
            WHERE series_fts MATCH :query
            ORDER BY rank
            LIMIT :limit
        """
        fts_result = await self._session.execute(
            text(sql),
            {"query": fts_query, "limit": limit * 2},
        )
        fts_rows = fts_result.fetchall()
        if not fts_rows:
            return []

        rowid_to_rank = {row[0]: row[1] for row in fts_rows}

        # Load only the root ``SeriesModel`` rows. ``SearchCatalogUseCase``
        # builds ``SearchItemOutput`` from root columns + ``localized`` JSON
        # only — it never touches ``series.seasons``. Skipping the
        # season → episode → file_variants chain avoids fanning out into
        # potentially thousands of rows per search (e.g. a 10-season,
        # 22-episode series with multi-resolution variants) just to be
        # discarded by the use case. Also keeps ``EpisodeMapper`` from
        # lazy-loading ``file_variants`` outside the session greenlet.
        stmt = select(SeriesModel).where(
            SeriesModel.id.in_(rowid_to_rank.keys()),
            SeriesModel.deleted_at.is_(None),
        )
        if genre:
            delimited = "," + SeriesModel.genres + ","
            stmt = stmt.where(delimited.contains(f",{genre},"))
        if year_min is not None:
            stmt = stmt.where(SeriesModel.start_year >= year_min)
        if year_max is not None:
            stmt = stmt.where(SeriesModel.start_year <= year_max)
        if allowed_library_ids is not None:
            stmt = stmt.where(
                SeriesModel.library_id.in_([library_id.value for library_id in allowed_library_ids])
            )

        result = await self._session.execute(stmt)
        models = result.scalars().unique().all()

        hits = [
            (SeriesMapper.to_entity(m, include_seasons=False), rowid_to_rank[m.id])
            for m in models
            if m.id in rowid_to_rank
        ]
        hits.sort(key=lambda h: h[1])
        return hits[:limit]


__all__ = ["SQLAlchemySeriesRepository"]
