"""SQLAlchemy implementation of MovieRepository."""

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.media.entities import Movie
from src.domain.media.repositories import MovieRepository
from src.domain.media.value_objects import FilePath, MovieId
from src.infrastructure.persistence.mappers import MovieMapper
from src.infrastructure.persistence.models import MovieModel


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
        stmt = select(MovieModel).where(
            MovieModel.external_id == str(movie_id),
            MovieModel.deleted_at.is_(None),
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
        # Generate ID if not present
        if movie.id is None:
            movie = movie.with_updates(id=MovieId.generate())

        # Check if the movie already exists (including soft-deleted for restore)
        stmt = select(MovieModel).where(MovieModel.external_id == str(movie.id))
        result = await self._session.execute(stmt)
        existing_model = result.scalar_one_or_none()

        # Restore if soft-deleted
        if existing_model is not None and existing_model.is_deleted:
            existing_model.restore()

        if existing_model is not None:
            # Update existing
            MovieMapper.update_model(existing_model, movie)
            await self._session.flush()
            await self._session.refresh(existing_model)
            return MovieMapper.to_entity(existing_model)

        # Create new
        model = MovieMapper.to_model(movie)
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)

        return MovieMapper.to_entity(model)

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
        stmt = select(MovieModel).where(MovieModel.deleted_at.is_(None)).order_by(MovieModel.title)
        result = await self._session.execute(stmt)
        models = result.scalars().all()

        return [MovieMapper.to_entity(model) for model in models]

    async def find_by_file_path(self, file_path: FilePath) -> Movie | None:
        """Find a movie by its file path (excluding soft-deleted).

        Args:
            file_path: The absolute file path.

        Returns:
            The Movie if found, None otherwise.
        """
        stmt = select(MovieModel).where(
            MovieModel.file_path == str(file_path),
            MovieModel.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()

        return None if model is None else MovieMapper.to_entity(model)


__all__ = ["SQLAlchemyMovieRepository"]
