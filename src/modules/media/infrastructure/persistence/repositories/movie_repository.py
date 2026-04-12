"""SQLAlchemy implementation of MovieRepository."""

from collections.abc import Sequence

from sqlalchemy import func, select
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

        await self._session.commit()

        # Reload with relationships to return a complete entity
        assert movie.id is not None
        result_entity = await self.find_by_id(movie.id)
        assert result_entity is not None
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
        await self._session.commit()
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


__all__ = ["SQLAlchemyMovieRepository"]
