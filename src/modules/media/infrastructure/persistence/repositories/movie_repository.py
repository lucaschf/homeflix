"""SQLAlchemy implementation of MovieRepository."""

import json
from collections.abc import Sequence

from sqlalchemy import and_, func, or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.building_blocks.application.pagination import (
    decode_cursor,
    decode_title_cursor,
    encode_cursor,
    encode_title_cursor,
)
from src.building_blocks.domain.pagination import PaginatedResult, Pagination
from src.modules.media.domain.entities import Movie
from src.modules.media.domain.repositories import MovieRepository
from src.modules.media.domain.repositories.movie_repository import (
    CreditsStatusRow,
    GenreRow,
    RemoteArtworkRow,
)
from src.modules.media.domain.value_objects import (
    ArtworkColumns,
    CreditsDetectionState,
    CreditsMarker,
    EpisodeId,
    FilePath,
    Genre,
    MovieId,
)
from src.modules.media.infrastructure.persistence.mappers import MovieMapper
from src.modules.media.infrastructure.persistence.models import (
    EpisodeModel,
    MediaFileModel,
    MovieModel,
)
from src.modules.media.infrastructure.persistence.repositories._artwork_helpers import (
    artwork_column_values,
    to_artwork_columns,
)
from src.modules.media.infrastructure.persistence.repositories._genre_helpers import (
    fetch_genre_paginated_page,
    fetch_genre_rows,
    localized_title_for,
    localized_title_sort_key,
)
from src.modules.media.infrastructure.persistence.repositories._path_prefix_helpers import (
    build_path_prefix_filters,
)
from src.shared_kernel.value_objects.library_id import LibraryId


def _movie_filter_conditions(
    *,
    allowed_library_ids: Sequence[LibraryId] | None,
    library_id: str | None,
    has_tmdb_id: bool | None,
    needs_enrichment_review: bool | None,
    fts_matching_ids: Sequence[int] | None,
) -> list:
    """Build SQLAlchemy ``WHERE`` clauses for the optional movie filters.

    Pulled out as a helper so ``list_paginated`` and its
    ``COUNT(*)`` partner stay in lock-step — adding a new filter
    means one edit here rather than two parallel branches drifting.

    ``fts_matching_ids`` is the result of pre-querying the
    ``movies_fts`` virtual table for the operator's ``q`` text.
    Caller resolves it once, before the page query, so the same
    id set scopes both ``SELECT`` and ``COUNT(*)``.
    """
    conditions: list = []
    if allowed_library_ids is not None:
        conditions.append(
            MovieModel.library_id.in_([library_id.value for library_id in allowed_library_ids])
        )
    if library_id is not None:
        conditions.append(MovieModel.library_id == library_id)
    if has_tmdb_id is not None:
        conditions.append(
            MovieModel.tmdb_id.is_not(None) if has_tmdb_id else MovieModel.tmdb_id.is_(None),
        )
    if needs_enrichment_review is not None:
        conditions.append(
            MovieModel.needs_enrichment_review.is_(True)
            if needs_enrichment_review
            else MovieModel.needs_enrichment_review.is_(False),
        )
    if fts_matching_ids is not None:
        conditions.append(MovieModel.id.in_(fts_matching_ids))
    return conditions


class SQLAlchemyMovieRepository(MovieRepository):
    """SQLAlchemy implementation of MovieRepository.

    Provides async database operations for Movie aggregates.

    Example:
        >>> repo = SQLAlchemyMovieRepository(session)
        >>> movie = await repo.find_by_id(MovieId("mov_abc123"))
    """

    def __init__(self, session: AsyncSession) -> None:
        """Initialize repository with database session.

        Args:
            session: SQLAlchemy async session.
        """
        self._session = session

    async def find_by_id(
        self,
        movie_id: MovieId,
        *,
        allowed_library_ids: Sequence[LibraryId] | None = None,
    ) -> Movie | None:
        """Find a movie by its ID.

        Args:
            movie_id: The movie's external ID.
            allowed_library_ids: Optional per-profile ACL filter.

        Returns:
            The Movie if found, None otherwise.
        """
        stmt = (
            select(MovieModel)
            .where(
                MovieModel.external_id == str(movie_id),
                MovieModel.deleted_at.is_(None),
            )
            .options(selectinload(MovieModel.file_variants))
        )
        if allowed_library_ids is not None:
            stmt = stmt.where(
                MovieModel.library_id.in_([library_id.value for library_id in allowed_library_ids])
            )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()

        return None if model is None else MovieMapper.to_entity(model)

    async def save(self, movie: Movie) -> Movie:
        """Persist a movie (create or update).

        Args:
            movie: The movie to save.

        Returns:
            The saved movie (with generated ID if new).
        """
        movie = movie.with_updates(id=MovieId.generate_if_absent(movie.id))

        # Check if the movie already exists (including soft-deleted for restore)
        stmt = (
            select(MovieModel)
            .where(MovieModel.external_id == str(movie.id))
            .options(selectinload(MovieModel.file_variants))
        )
        result = await self._session.execute(stmt)
        existing_model = result.scalar_one_or_none()

        # Restore if soft-deleted
        if existing_model is not None and existing_model.is_deleted:
            existing_model.restore()

        if existing_model is not None:
            # Update existing
            MovieMapper.update_model(existing_model, movie)
            await self._session.flush()
        else:
            # Create new
            model = MovieMapper.to_model(movie)
            self._session.add(model)
            await self._session.flush()

        # Reload with relationships to return a complete entity.
        # Transaction commit is the Unit of Work's responsibility.
        if movie.id is None:
            raise RuntimeError("Movie id must be assigned before reload")
        result_entity = await self.find_by_id(movie.id)
        if result_entity is None:
            raise RuntimeError(f"Movie {movie.id} disappeared between flush and reload")
        return result_entity

    async def delete(self, movie_id: MovieId) -> bool:
        """Soft delete a movie by ID.

        Args:
            movie_id: The movie's external ID.

        Returns:
            True if deleted, False if not found.
        """
        stmt = select(MovieModel).where(
            MovieModel.external_id == str(movie_id),
            MovieModel.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()

        if model is None:
            return False

        model.soft_delete()
        await self._session.flush()
        return True

    async def list_all(self) -> Sequence[Movie]:
        """List all movies (excluding soft-deleted).

        Returns:
            Sequence of all movies ordered by title.
        """
        stmt = (
            select(MovieModel)
            .where(MovieModel.deleted_at.is_(None))
            .options(selectinload(MovieModel.file_variants))
            .order_by(MovieModel.title)
        )
        result = await self._session.execute(stmt)
        models = result.scalars().all()

        return [MovieMapper.to_entity(model) for model in models]

    async def list_paginated(
        self,
        cursor: str | None,
        limit: int,
        *,
        include_total: bool = False,
        allowed_library_ids: Sequence[LibraryId] | None = None,
        library_id: str | None = None,
        has_tmdb_id: bool | None = None,
        needs_enrichment_review: bool | None = None,
        q: str | None = None,
    ) -> PaginatedResult[Movie]:
        """List movies in a single cursor-paginated page.

        Sorted by ``id DESC`` so the most recently inserted rows
        appear first. Internal autoincrement id is monotonic with
        insertion and matches "newest by ``created_at``" in practice
        because ``created_at`` is server-generated on insert and never
        edited later — see ``building_blocks/application/pagination.py``
        for the full justification.

        Soft-deleted rows are filtered out the same way as ``list_all``.
        Fetches ``limit + 1`` rows to detect ``has_more`` cheaply
        without an extra query.

        The admin-facing filters (``library_id``, ``has_tmdb_id``,
        ``needs_enrichment_review``) compose with the per-profile ACL
        in ``allowed_library_ids``: when both are present the row must
        satisfy *both* constraints. Admin pages call without ACL
        kwargs and pass these filters; the user-facing list does the
        inverse.

        ``q`` is delegated to the ``movies_fts`` virtual table so the
        same i18n-aware tokenizer + indexed surface (title,
        original_title, synopsis, tagline, genres, cast, directors,
        writers, collection_name, localized_*) used by the catalog
        search overlay backs the admin's text filter. The FTS5
        ``MATCH`` resolves to a set of internal ids that is then
        composed as ``id IN (...)`` so cursor pagination remains
        ordered by ``id DESC`` rather than relevance — the admin
        flow benefits more from a stable page-by-page walk than a
        ranked top-N.
        """
        fts_matching_ids: list[int] | None = None
        if q and q.strip():
            fts_matching_ids = await _movie_fts_matching_ids(self._session, q)
            if not fts_matching_ids:
                return PaginatedResult(
                    items=[],
                    pagination=Pagination(next_cursor=None, has_more=False),
                    total_count=0 if include_total else None,
                )

        conditions = _movie_filter_conditions(
            allowed_library_ids=allowed_library_ids,
            library_id=library_id,
            has_tmdb_id=has_tmdb_id,
            needs_enrichment_review=needs_enrichment_review,
            fts_matching_ids=fts_matching_ids,
        )

        decoded = decode_cursor(cursor)

        stmt = (
            select(MovieModel)
            .where(MovieModel.deleted_at.is_(None), *conditions)
            .options(selectinload(MovieModel.file_variants))
        )

        if decoded is not None:
            stmt = stmt.where(MovieModel.id < decoded.id)

        stmt = stmt.order_by(MovieModel.id.desc()).limit(limit + 1)

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
                .select_from(MovieModel)
                .where(MovieModel.deleted_at.is_(None), *conditions)
            )
            total_count = (await self._session.execute(count_stmt)).scalar_one()

        return PaginatedResult(
            items=[MovieMapper.to_entity(m) for m in models],
            pagination=Pagination(next_cursor=next_cursor, has_more=has_more),
            total_count=total_count,
        )

    async def list_recently_added(
        self,
        limit: int,
        *,
        allowed_library_ids: Sequence[LibraryId] | None = None,
    ) -> Sequence[Movie]:
        """Return the top ``limit`` non-deleted movies, newest first.

        Same ``id DESC`` ordering as ``list_paginated`` — autoincrement
        id is monotonic with insertion so it matches "newest by
        ``created_at``" without paying for the SQLite ``func.now()``
        precision quirk that ruled out a composite cursor on the
        paginated path.
        """
        stmt = (
            select(MovieModel)
            .where(MovieModel.deleted_at.is_(None))
            .options(selectinload(MovieModel.file_variants))
        )
        if allowed_library_ids is not None:
            stmt = stmt.where(
                MovieModel.library_id.in_([library_id.value for library_id in allowed_library_ids])
            )
        stmt = stmt.order_by(MovieModel.id.desc()).limit(limit)
        result = await self._session.execute(stmt)
        return [MovieMapper.to_entity(m) for m in result.scalars().all()]

    async def list_genre_rows(
        self,
        lang: str,
        *,
        allowed_library_ids: Sequence[LibraryId] | None = None,
    ) -> Sequence[GenreRow]:
        """Project the genre columns of every non-deleted movie row."""
        return await fetch_genre_rows(
            self._session,
            MovieModel,
            lang,
            allowed_library_ids=allowed_library_ids,
        )

    async def list_paginated_by_genre(
        self,
        genre: Genre,
        cursor: str | None,
        limit: int,
        *,
        lang: str = "en",
        allowed_library_ids: Sequence[LibraryId] | None = None,
    ) -> PaginatedResult[Movie]:
        """List movies for a single genre, paginated and sorted by title.

        Delegates the SQL boilerplate (delimited LIKE filter,
        localized ``LOWER(COALESCE(localized[lang].title, title))``
        cursor, fetch N+1 trick, per-item cursor population) to the
        shared ``fetch_genre_paginated_page`` helper so this method and
        its series counterpart can't drift apart.
        """
        return await fetch_genre_paginated_page(
            session=self._session,
            model=MovieModel,
            mapper_to_entity=MovieMapper.to_entity,
            options=[selectinload(MovieModel.file_variants)],
            genre=genre,
            cursor=cursor,
            limit=limit,
            lang=lang,
            allowed_library_ids=allowed_library_ids,
        )

    async def list_paginated_by_cast_member(
        self,
        actor_name: str,
        cursor: str | None,
        limit: int,
        *,
        lang: str = "en",
        allowed_library_ids: Sequence[LibraryId] | None = None,
    ) -> PaginatedResult[Movie]:
        """List movies whose ``cast`` JSON contains an entry for ``actor_name``.

        Filters with a SQL LIKE against the JSON-serialized ``cast``
        text column. ``_serialize_cast`` writes entries with ``json.dumps``
        and default separators, so ``"name": "<name>"`` (with a space
        after the colon) appears verbatim in storage — the needle
        builder mirrors that format. Matching by JSON-encoded form
        rather than by raw substring keeps a name from false-positive
        matching against a ``role`` or ``profile_path`` field that
        happened to contain the same text.

        Pagination matches ``list_paginated_by_genre`` (title cursor,
        ``LOWER(title), id`` order, fetch ``limit + 1`` for ``has_more``)
        so the actor page can reuse the same cursor-handling
        conventions as the genre page.
        """
        decoded = decode_title_cursor(cursor)

        # JSON-encode the actor name so special characters (``"``, ``\``,
        # accented letters under ``ensure_ascii=False``) match the form
        # the row was serialized with. Outer quotes are preserved so
        # the needle below matches whole-string equality, not a prefix.
        name_json = json.dumps(actor_name, ensure_ascii=False)
        needle = f'"name": {name_json}'
        # Escape SQL LIKE wildcards (``%`` and ``_``) plus the escape
        # char itself so an actor whose name contains those characters
        # doesn't widen the match. A trailing-only ``%`` would let
        # ``"Jane Doe"`` match ``"Jane Doe Jr."`` since both names
        # share the same prefix; the ``%...%`` wrap below already
        # prevents that because the needle includes the closing quote
        # of ``name_json``.
        needle_escaped = needle.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

        title_lower = localized_title_sort_key(MovieModel, lang)

        stmt = (
            select(MovieModel)
            .where(
                MovieModel.deleted_at.is_(None),
                MovieModel.cast.is_not(None),
                MovieModel.cast.like(f"%{needle_escaped}%", escape="\\"),
            )
            .options(selectinload(MovieModel.file_variants))
        )

        if allowed_library_ids is not None:
            stmt = stmt.where(
                MovieModel.library_id.in_([library_id.value for library_id in allowed_library_ids])
            )

        if decoded is not None:
            stmt = stmt.where(
                or_(
                    title_lower > decoded.title,
                    and_(title_lower == decoded.title, MovieModel.id > decoded.id),
                )
            )

        stmt = stmt.order_by(title_lower.asc(), MovieModel.id.asc()).limit(limit + 1)

        result = await self._session.execute(stmt)
        rows = list(result.scalars().all())

        has_more = len(rows) > limit
        if has_more:
            rows = rows[:limit]

        next_cursor: str | None = None
        if has_more and rows:
            next_cursor = encode_title_cursor(
                localized_title_for(rows[-1].localized, rows[-1].title, lang),
                rows[-1].id,
            )

        return PaginatedResult(
            items=[MovieMapper.to_entity(m) for m in rows],
            pagination=Pagination(next_cursor=next_cursor, has_more=has_more),
            total_count=None,
        )

    async def find_random(
        self,
        limit: int,
        *,
        with_backdrop: bool = False,
        allowed_library_ids: Sequence[LibraryId] | None = None,
    ) -> Sequence[Movie]:
        """Return random movies."""
        from sqlalchemy.sql.expression import func

        stmt = (
            select(MovieModel)
            .where(MovieModel.deleted_at.is_(None))
            .options(selectinload(MovieModel.file_variants))
        )
        if with_backdrop:
            stmt = stmt.where(
                MovieModel.backdrop_path.is_not(None),
                MovieModel.backdrop_path != "",
            )
        if allowed_library_ids is not None:
            stmt = stmt.where(
                MovieModel.library_id.in_([library_id.value for library_id in allowed_library_ids])
            )
        stmt = stmt.order_by(func.random()).limit(limit)
        result = await self._session.execute(stmt)
        return [MovieMapper.to_entity(m) for m in result.scalars().all()]

    async def find_by_ids(
        self,
        movie_ids: Sequence[MovieId],
        *,
        allowed_library_ids: Sequence[LibraryId] | None = None,
    ) -> dict[str, Movie]:
        """Find multiple movies by their IDs in a single query."""
        if not movie_ids:
            return {}

        ext_ids = [str(mid) for mid in movie_ids]
        stmt = (
            select(MovieModel)
            .where(
                MovieModel.external_id.in_(ext_ids),
                MovieModel.deleted_at.is_(None),
            )
            .options(selectinload(MovieModel.file_variants))
        )
        if allowed_library_ids is not None:
            stmt = stmt.where(
                MovieModel.library_id.in_([library_id.value for library_id in allowed_library_ids])
            )
        result = await self._session.execute(stmt)
        return {model.external_id: MovieMapper.to_entity(model) for model in result.scalars().all()}

    async def find_by_tmdb_ids(
        self,
        tmdb_ids: Sequence[int],
        *,
        allowed_library_ids: Sequence[LibraryId] | None = None,
    ) -> dict[int, Movie]:
        """Find movies whose ``tmdb_id`` matches any of ``tmdb_ids``.

        Used by ``GetRelatedMovies`` to resolve the subset of TMDB's
        recommendation list that exists locally. Returning a dict
        keyed by ``tmdb_id`` lets the caller preserve TMDB's
        relevance ordering by iterating the request list.
        """
        if not tmdb_ids:
            return {}
        stmt = (
            select(MovieModel)
            .where(
                MovieModel.tmdb_id.in_(tmdb_ids),
                MovieModel.deleted_at.is_(None),
            )
            .options(selectinload(MovieModel.file_variants))
        )
        if allowed_library_ids is not None:
            stmt = stmt.where(
                MovieModel.library_id.in_([library_id.value for library_id in allowed_library_ids])
            )
        result = await self._session.execute(stmt)
        return {
            model.tmdb_id: MovieMapper.to_entity(model)
            for model in result.scalars().all()
            if model.tmdb_id is not None
        }

    async def find_all_by_tmdb_id(self, tmdb_id: int) -> list[Movie]:
        """Return every non-deleted movie with the given TMDB id.

        Preserves duplicates (unlike ``find_by_tmdb_ids`` which keys
        by tmdb_id). No ACL filter — see the ABC docstring.
        """
        stmt = (
            select(MovieModel)
            .where(
                MovieModel.tmdb_id == tmdb_id,
                MovieModel.deleted_at.is_(None),
            )
            .options(selectinload(MovieModel.file_variants))
        )
        result = await self._session.execute(stmt)
        return [MovieMapper.to_entity(model) for model in result.scalars().all()]

    async def find_all_by_year(self, year: int) -> list[Movie]:
        """Return every non-deleted movie released in ``year``.

        Feeds the ADR-015 ``(normalized_original_title, year)`` dedup
        fallback. No ACL filter — see the ABC docstring.
        """
        stmt = (
            select(MovieModel)
            .where(
                MovieModel.year == year,
                MovieModel.deleted_at.is_(None),
            )
            .options(selectinload(MovieModel.file_variants))
        )
        result = await self._session.execute(stmt)
        return [MovieMapper.to_entity(model) for model in result.scalars().all()]

    async def find_by_file_path(self, file_path: FilePath) -> Movie | None:
        """Find a movie by any of its file variant paths.

        Args:
            file_path: The absolute file path.

        Returns:
            The Movie if found, None otherwise.
        """
        # Search in file_variants table
        stmt = (
            select(MovieModel)
            .join(MediaFileModel, MediaFileModel.movie_id == MovieModel.id)
            .where(
                MediaFileModel.file_path == str(file_path),
                MovieModel.deleted_at.is_(None),
            )
            .options(selectinload(MovieModel.file_variants))
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()

        if model is not None:
            return MovieMapper.to_entity(model)

        # Fallback to flat column for backward compatibility
        stmt = (
            select(MovieModel)
            .where(
                MovieModel.file_path == str(file_path),
                MovieModel.deleted_at.is_(None),
            )
            .options(selectinload(MovieModel.file_variants))
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()

        return None if model is None else MovieMapper.to_entity(model)

    async def find_needs_enrichment_review(
        self,
        *,
        allowed_library_ids: Sequence[LibraryId] | None = None,
    ) -> Sequence[Movie]:
        """Return movies with the review flag set, newest-first."""
        conditions = [
            MovieModel.deleted_at.is_(None),
            MovieModel.needs_enrichment_review.is_(True),
        ]
        if allowed_library_ids is not None:
            allowed = list(allowed_library_ids)
            if not allowed:
                return []
            conditions.append(MovieModel.library_id.in_(allowed))

        stmt = (
            select(MovieModel)
            .where(*conditions)
            .options(selectinload(MovieModel.file_variants))
            .order_by(MovieModel.updated_at.desc())
        )
        result = await self._session.execute(stmt)
        return [MovieMapper.to_entity(model) for model in result.scalars().all()]

    async def transfer_file_variants_to_episode(
        self,
        movie_id: MovieId,
        episode_id: EpisodeId,
    ) -> int:
        """Re-FK media_files from a movie's row to an episode's row.

        Looks up both internal primary keys via the external ids,
        then a single ``UPDATE`` rewrites the FK pair on every matching
        row. ``movie_id`` is set to ``NULL`` so the cascade triggered
        by the subsequent movie soft-delete doesn't sweep the rows
        we just relocated.
        """
        movie_pk_stmt = select(MovieModel.id).where(
            MovieModel.external_id == str(movie_id),
        )
        episode_pk_stmt = select(EpisodeModel.id).where(
            EpisodeModel.external_id == str(episode_id),
        )
        movie_pk = (await self._session.execute(movie_pk_stmt)).scalar_one_or_none()
        episode_pk = (await self._session.execute(episode_pk_stmt)).scalar_one_or_none()
        if movie_pk is None or episode_pk is None:
            return 0

        result = await self._session.execute(
            text(
                "UPDATE media_files "
                "SET movie_id = NULL, episode_id = :episode_pk "
                "WHERE movie_id = :movie_pk"
            ),
            {"movie_pk": movie_pk, "episode_pk": episode_pk},
        )
        return result.rowcount or 0

    async def transfer_file_variants_between_movies(
        self,
        source_movie_id: MovieId,
        target_movie_id: MovieId,
    ) -> int:
        """Re-FK media_files from one movie's row to another's.

        Mirrors ``transfer_file_variants_to_episode`` — looks up both
        internal primary keys via the external ids, then a single
        ``UPDATE`` rewrites the ``movie_id`` on every matching row.
        """
        src_pk_stmt = select(MovieModel.id).where(
            MovieModel.external_id == str(source_movie_id),
        )
        tgt_pk_stmt = select(MovieModel.id).where(
            MovieModel.external_id == str(target_movie_id),
        )
        src_pk = (await self._session.execute(src_pk_stmt)).scalar_one_or_none()
        tgt_pk = (await self._session.execute(tgt_pk_stmt)).scalar_one_or_none()
        if src_pk is None or tgt_pk is None:
            return 0

        result = await self._session.execute(
            text(
                "UPDATE media_files SET movie_id = :tgt_pk WHERE movie_id = :src_pk",
            ),
            {"src_pk": src_pk, "tgt_pk": tgt_pk},
        )
        # Raw UPDATE bypasses the identity map, so any cached
        # MovieModel instances still report the old file_variants
        # relationship. Expire them so the next query reloads fresh
        # from the database.
        self._session.expire_all()
        return result.rowcount or 0

    async def find_missing_scrub_preview(self, limit: int) -> Sequence[Movie]:
        """Return up to ``limit`` movies whose ``scrub_preview_path`` is null.

        Sorted by ``id ASC`` so repeated runs make steady forward
        progress through the catalog instead of churning on the same
        head of the list. ``file_variants`` is eager-loaded because the
        backfill caller needs ``primary_file.file_path``.
        """
        stmt = (
            select(MovieModel)
            .where(
                MovieModel.deleted_at.is_(None),
                MovieModel.scrub_preview_path.is_(None),
            )
            .options(selectinload(MovieModel.file_variants))
            .order_by(MovieModel.id.asc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return [MovieMapper.to_entity(model) for model in result.scalars().all()]

    async def find_with_remote_artwork(self, limit: int) -> Sequence[RemoteArtworkRow]:
        """Return up to ``limit`` movies whose artwork is still a remote URL.

        Projects just the four columns the mirror job needs (external id +
        the three artwork URLs) so it never loads entities or their file
        variants. ``LIKE 'http%'`` matches the persisted full provider
        URLs; already-mirrored ``/api/v1/artwork/...`` paths don't match.
        """
        stmt = (
            select(
                MovieModel.external_id,
                MovieModel.poster_path,
                MovieModel.backdrop_path,
                MovieModel.logo_path,
            )
            .where(
                MovieModel.deleted_at.is_(None),
                or_(
                    MovieModel.poster_path.like("http%"),
                    MovieModel.backdrop_path.like("http%"),
                    MovieModel.logo_path.like("http%"),
                ),
            )
            .order_by(MovieModel.id.asc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return [
            RemoteArtworkRow(
                media_id=row.external_id,
                artwork=to_artwork_columns(row.poster_path, row.backdrop_path, row.logo_path),
            )
            for row in result.all()
        ]

    async def update_movie_artwork(self, movie_id: MovieId, artwork: ArtworkColumns) -> None:
        """Set the three artwork columns for one movie by external id."""
        await self._session.execute(
            update(MovieModel)
            .where(MovieModel.external_id == movie_id.value)
            .values(**artwork_column_values(artwork))
        )

    async def count_credits_states(self) -> dict[str, int]:
        """Return ``{credits_detection_state: count}`` over non-deleted movies."""
        stmt = (
            select(MovieModel.credits_detection_state, func.count())
            .where(MovieModel.deleted_at.is_(None))
            .group_by(MovieModel.credits_detection_state)
        )
        result = await self._session.execute(stmt)
        return dict(result.all())

    async def total_file_size_by_library(self) -> dict[str, int]:
        """Sum primary-file bytes per library over non-deleted movies."""
        stmt = (
            select(
                MovieModel.library_id,
                func.coalesce(func.sum(MovieModel.file_size), 0),
            )
            .where(MovieModel.deleted_at.is_(None))
            .group_by(MovieModel.library_id)
        )
        result = await self._session.execute(stmt)
        return {library_id: int(total) for library_id, total in result.all()}

    async def list_credits_status(
        self, state: str | None, limit: int, offset: int
    ) -> tuple[Sequence[CreditsStatusRow], int]:
        """Return a page of movie credits-status rows + total (newest first)."""
        conditions = [MovieModel.deleted_at.is_(None)]
        if state is not None:
            conditions.append(MovieModel.credits_detection_state == state)

        total = (
            await self._session.execute(
                select(func.count()).select_from(MovieModel).where(*conditions)
            )
        ).scalar_one()

        stmt = (
            select(
                MovieModel.external_id,
                MovieModel.title,
                MovieModel.credits_detection_state,
                MovieModel.credits_start_seconds,
                MovieModel.credits_source,
                MovieModel.credits_confidence,
            )
            .where(*conditions)
            # SQLite sorts NULLs last under DESC, so freshly-marked rows
            # surface first and never-marked ones sink to the bottom.
            .order_by(MovieModel.credits_detected_at.desc(), MovieModel.title.asc())
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
            )
            for r in rows
        ]
        return items, int(total)

    async def find_pending_credits_detection(self, limit: int) -> Sequence[Movie]:
        """Return NOT_STARTED-credits movies with file variants loaded."""
        stmt = (
            select(MovieModel)
            .where(
                MovieModel.deleted_at.is_(None),
                MovieModel.credits_detection_state == CreditsDetectionState.NOT_STARTED.value,
            )
            .options(selectinload(MovieModel.file_variants))
            .order_by(MovieModel.id.asc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return [MovieMapper.to_entity(model) for model in result.scalars().all()]

    async def update_movie_credits(
        self,
        movie_id: MovieId,
        marker: CreditsMarker | None,
        state: CreditsDetectionState,
    ) -> bool:
        """Direct UPDATE of the 4 credits columns + state on the movies row."""
        values: dict[str, object] = {"credits_detection_state": state.value}
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
            update(MovieModel)
            .where(
                MovieModel.external_id == str(movie_id),
                MovieModel.deleted_at.is_(None),
            )
            .values(**values)
        )
        result = await self._session.execute(stmt)
        return bool(result.rowcount)

    async def count_under_paths(self, paths: Sequence[str]) -> int:
        r"""Count non-deleted movies whose ``file_path`` is under any of ``paths``.

        Matches both ``\`` and ``/`` separators so the query is
        cross-platform — a library row written on Linux still matches
        a filter coming from a Windows client and vice versa. See
        ``_path_prefix_helpers.build_path_prefix_filters`` for the
        normalization rules shared with the series repo.
        """
        prefix_filters = build_path_prefix_filters(MovieModel.file_path, paths)
        if not prefix_filters:
            return 0
        stmt = (
            select(func.count())
            .select_from(MovieModel)
            .where(
                MovieModel.deleted_at.is_(None),
                MovieModel.file_path.is_not(None),
                or_(*prefix_filters),
            )
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def count(self) -> int:
        """Return the total number of non-deleted movies."""
        stmt = select(func.count()).select_from(MovieModel).where(MovieModel.deleted_at.is_(None))
        result = await self._session.execute(stmt)
        return int(result.scalar_one())

    async def search(
        self,
        query: str,
        *,
        genre: str | None = None,
        year_min: int | None = None,
        year_max: int | None = None,
        limit: int = 20,
        allowed_library_ids: Sequence[LibraryId] | None = None,
    ) -> list[tuple[Movie, float]]:
        """Full-text search using FTS5.

        Queries the ``movies_fts`` virtual table for rows matching
        ``query``, joins back to the ``movies`` table to load the
        full ORM model, and applies optional genre/year filters as
        ``WHERE`` clauses on the main table.

        FTS5 query syntax: ``*`` suffix triggers prefix matching
        (e.g. ``incep*`` → Inception). The repository appends ``*``
        automatically when the query doesn't already contain it so
        type-ahead works out of the box.
        """
        fts_query = _prepare_fts_query(query)
        if not fts_query:
            return []

        # Step 1: FTS5 MATCH to get matching rowids + rank
        sql = """
            SELECT movies_fts.rowid, bm25(movies_fts) AS rank
            FROM movies_fts
            WHERE movies_fts MATCH :query
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

        # Step 2: Load only the root MovieModel rows. ``SearchCatalogUseCase``
        # builds ``SearchItemOutput`` from root columns + ``localized`` JSON
        # only — it never touches ``movie.files``. Skipping ``file_variants``
        # here avoids a fan-out of one extra query plus N rows of file
        # metadata per hit, which on a 30-result search with rich
        # multi-resolution variants meant thousands of rows fetched and
        # immediately discarded.
        stmt = select(MovieModel).where(
            MovieModel.id.in_(rowid_to_rank.keys()),
            MovieModel.deleted_at.is_(None),
        )
        if genre:
            delimited = "," + MovieModel.genres + ","
            stmt = stmt.where(delimited.contains(f",{genre},"))
        if year_min is not None:
            stmt = stmt.where(MovieModel.year >= year_min)
        if year_max is not None:
            stmt = stmt.where(MovieModel.year <= year_max)
        if allowed_library_ids is not None:
            stmt = stmt.where(
                MovieModel.library_id.in_([library_id.value for library_id in allowed_library_ids])
            )

        result = await self._session.execute(stmt)
        models = result.scalars().all()

        # Step 3: Map to shallow entities (files=[]) and pair with rank.
        hits = [
            (MovieMapper.to_entity(m, include_files=False), rowid_to_rank[m.id])
            for m in models
            if m.id in rowid_to_rank
        ]
        hits.sort(key=lambda h: h[1])
        return hits[:limit]


async def _movie_fts_matching_ids(session: AsyncSession, query: str) -> list[int]:
    """Resolve ``query`` against ``movies_fts`` and return matching ids.

    Used by the admin Catalog list to delegate text matching to the
    same FTS5 index that powers the catalog search overlay — same
    tokenizer, same column surface (title, original_title, synopsis,
    tagline, genres, cast, directors, writers, collection_name and
    every ``localized_*`` projection of the JSON ``localized`` blob).

    Returns ``[]`` when the sanitized query is empty or no rows
    match — caller treats both as "no hits" and short-circuits with
    an empty page.

    No ``LIMIT``: the caller composes the result as ``id IN (...)``
    and re-orders by ``id DESC`` for cursor pagination, so it needs
    the full hit set rather than a relevance-ranked top-N.
    """
    fts_query = _prepare_fts_query(query)
    if not fts_query:
        return []
    sql = """
        SELECT rowid FROM movies_fts
        WHERE movies_fts MATCH :query
    """
    result = await session.execute(text(sql), {"query": fts_query})
    return [row[0] for row in result.fetchall()]


def _prepare_fts_query(query: str) -> str:
    """Sanitize and prepare the raw user query for FTS5 MATCH.

    Splits the input into tokens, strips characters that FTS5 would
    interpret as operators (``-``, ``+``, ``"``), and appends ``*``
    to the last token for prefix matching (type-ahead). Returns an
    empty string if the query has no usable tokens, signalling the
    caller to short-circuit with an empty result.
    """
    tokens = []
    for word in query.strip().split():
        cleaned = word.strip("\"'-+")
        if cleaned:
            tokens.append(cleaned)
    if not tokens:
        return ""
    # Append * to the last token for prefix matching
    tokens[-1] = tokens[-1] + "*"
    return " ".join(tokens)


__all__ = ["SQLAlchemyMovieRepository"]
