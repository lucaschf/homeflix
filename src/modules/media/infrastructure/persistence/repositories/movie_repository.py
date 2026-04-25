"""SQLAlchemy implementation of MovieRepository."""

from collections.abc import Sequence

from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.building_blocks.application.pagination import (
    PaginatedResult,
    Pagination,
    decode_cursor,
    encode_cursor,
)
from src.modules.media.domain.entities import Movie
from src.modules.media.domain.repositories import MovieRepository
from src.modules.media.domain.repositories.movie_repository import GenreRow
from src.modules.media.domain.value_objects import FilePath, Genre, MovieId
from src.modules.media.infrastructure.persistence.mappers import MovieMapper
from src.modules.media.infrastructure.persistence.models import MediaFileModel, MovieModel
from src.modules.media.infrastructure.persistence.repositories._genre_helpers import (
    fetch_genre_paginated_page,
    fetch_genre_rows,
)
from src.modules.media.infrastructure.persistence.repositories._path_prefix_helpers import (
    build_path_prefix_filters,
)


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

    async def find_by_id(self, movie_id: MovieId) -> Movie | None:
        """Find a movie by its ID.

        Args:
            movie_id: The movie's external ID.

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
        """
        decoded = decode_cursor(cursor)

        stmt = (
            select(MovieModel)
            .where(MovieModel.deleted_at.is_(None))
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
                select(func.count()).select_from(MovieModel).where(MovieModel.deleted_at.is_(None))
            )
            total_count = (await self._session.execute(count_stmt)).scalar_one()

        return PaginatedResult(
            items=[MovieMapper.to_entity(m) for m in models],
            pagination=Pagination(next_cursor=next_cursor, has_more=has_more),
            total_count=total_count,
        )

    async def list_genre_rows(self, lang: str) -> Sequence[GenreRow]:
        """Project the genre columns of every non-deleted movie row."""
        return await fetch_genre_rows(self._session, MovieModel, lang)

    async def list_paginated_by_genre(
        self,
        genre: Genre,
        cursor: str | None,
        limit: int,
    ) -> PaginatedResult[Movie]:
        """List movies for a single genre, paginated and sorted by title.

        Delegates the SQL boilerplate (delimited LIKE filter,
        ``LOWER(title)`` cursor, fetch N+1 trick, per-item cursor
        population) to the shared ``fetch_genre_paginated_page``
        helper so this method and its series counterpart can't drift
        apart.
        """
        return await fetch_genre_paginated_page(
            session=self._session,
            model=MovieModel,
            mapper_to_entity=MovieMapper.to_entity,
            options=[selectinload(MovieModel.file_variants)],
            genre=genre,
            cursor=cursor,
            limit=limit,
        )

    async def find_random(self, limit: int, *, with_backdrop: bool = False) -> Sequence[Movie]:
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
        stmt = stmt.order_by(func.random()).limit(limit)
        result = await self._session.execute(stmt)
        return [MovieMapper.to_entity(m) for m in result.scalars().all()]

    async def find_by_ids(self, movie_ids: Sequence[MovieId]) -> dict[str, Movie]:
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
        result = await self._session.execute(stmt)
        return {model.external_id: MovieMapper.to_entity(model) for model in result.scalars().all()}

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

    async def search(
        self,
        query: str,
        *,
        genre: str | None = None,
        year_min: int | None = None,
        year_max: int | None = None,
        limit: int = 20,
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
