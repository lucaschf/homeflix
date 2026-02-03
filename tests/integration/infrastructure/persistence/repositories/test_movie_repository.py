"""Integration tests for SQLAlchemyMovieRepository."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.media.entities import Movie
from src.domain.media.value_objects import (
    Duration,
    FilePath,
    Genre,
    MovieId,
    Resolution,
    Title,
    Year,
)
from src.infrastructure.persistence.repositories import SQLAlchemyMovieRepository


def _create_movie(
    title: str = "Test Movie",
    year: int = 2024,
    duration: int = 7200,
    file_path: str = "/movies/test.mkv",
    file_size: int = 1_000_000_000,
    resolution: str = "1080p",
    movie_id: MovieId | None = None,
    **kwargs,
) -> Movie:
    """Create a Movie entity for testing."""
    return Movie(
        id=movie_id or MovieId.generate(),
        title=Title(title),
        year=Year(year),
        duration=Duration(duration),
        file_path=FilePath(file_path),
        file_size=file_size,
        resolution=Resolution(resolution),
        **kwargs,
    )


@pytest.mark.integration
class TestSQLAlchemyMovieRepository:
    """Integration tests for movie repository operations."""

    async def test_save_creates_new_movie(self, db_session: AsyncSession) -> None:
        """Test that save persists a new movie."""
        repo = SQLAlchemyMovieRepository(db_session)
        movie = _create_movie(title="Inception", year=2010)

        saved = await repo.save(movie)

        assert saved.id == movie.id
        assert saved.title.value == "Inception"
        assert saved.year.value == 2010

    async def test_save_updates_existing_movie(self, db_session: AsyncSession) -> None:
        """Test that save updates an existing movie."""
        repo = SQLAlchemyMovieRepository(db_session)
        movie = _create_movie(title="Original Title")
        await repo.save(movie)

        # Update the movie
        updated_movie = Movie(
            id=movie.id,
            title=Title("Updated Title"),
            year=movie.year,
            duration=movie.duration,
            file_path=movie.file_path,
            file_size=movie.file_size,
            resolution=movie.resolution,
        )
        saved = await repo.save(updated_movie)

        assert saved.title.value == "Updated Title"

        # Verify in database
        fetched = await repo.find_by_id(movie.id)  # type: ignore[arg-type]
        assert fetched is not None
        assert fetched.title.value == "Updated Title"

    async def test_find_by_id_returns_movie(self, db_session: AsyncSession) -> None:
        """Test that find_by_id returns existing movie."""
        repo = SQLAlchemyMovieRepository(db_session)
        movie = _create_movie(title="The Matrix")
        await repo.save(movie)

        found = await repo.find_by_id(movie.id)  # type: ignore[arg-type]

        assert found is not None
        assert found.id == movie.id
        assert found.title.value == "The Matrix"

    async def test_find_by_id_returns_none_for_nonexistent(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Test that find_by_id returns None for non-existent movie."""
        repo = SQLAlchemyMovieRepository(db_session)

        found = await repo.find_by_id(MovieId.generate())

        assert found is None

    async def test_delete_removes_movie(self, db_session: AsyncSession) -> None:
        """Test that delete removes an existing movie."""
        repo = SQLAlchemyMovieRepository(db_session)
        movie = _create_movie()
        await repo.save(movie)

        deleted = await repo.delete(movie.id)  # type: ignore[arg-type]

        assert deleted is True
        assert await repo.find_by_id(movie.id) is None  # type: ignore[arg-type]

    async def test_delete_returns_false_for_nonexistent(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Test that delete returns False for non-existent movie."""
        repo = SQLAlchemyMovieRepository(db_session)

        deleted = await repo.delete(MovieId.generate())

        assert deleted is False

    async def test_list_all_returns_all_movies(self, db_session: AsyncSession) -> None:
        """Test that list_all returns all movies ordered by title."""
        repo = SQLAlchemyMovieRepository(db_session)
        movie1 = _create_movie(title="Zebra Movie", file_path="/movies/zebra.mkv")
        movie2 = _create_movie(title="Alpha Movie", file_path="/movies/alpha.mkv")
        movie3 = _create_movie(title="Beta Movie", file_path="/movies/beta.mkv")

        await repo.save(movie1)
        await repo.save(movie2)
        await repo.save(movie3)

        movies = await repo.list_all()

        assert len(movies) == 3
        # Should be ordered by title
        assert movies[0].title.value == "Alpha Movie"
        assert movies[1].title.value == "Beta Movie"
        assert movies[2].title.value == "Zebra Movie"

    async def test_list_all_returns_empty_when_no_movies(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Test that list_all returns empty sequence when no movies exist."""
        repo = SQLAlchemyMovieRepository(db_session)

        movies = await repo.list_all()

        assert len(movies) == 0

    async def test_find_by_file_path_returns_movie(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Test that find_by_file_path finds movie by its file path."""
        repo = SQLAlchemyMovieRepository(db_session)
        movie = _create_movie(file_path="/media/movies/inception.mkv")
        await repo.save(movie)

        found = await repo.find_by_file_path(FilePath("/media/movies/inception.mkv"))

        assert found is not None
        assert found.id == movie.id

    async def test_find_by_file_path_returns_none_for_nonexistent(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Test that find_by_file_path returns None for unknown path."""
        repo = SQLAlchemyMovieRepository(db_session)

        found = await repo.find_by_file_path(FilePath("/nonexistent/path.mkv"))

        assert found is None

    async def test_save_movie_with_all_optional_fields(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Test saving a movie with all optional fields populated."""
        repo = SQLAlchemyMovieRepository(db_session)
        movie = _create_movie(
            title="Full Movie",
            original_title=Title("Original Full Movie"),
            synopsis="A test movie with all fields.",
            poster_path=FilePath("/posters/full.jpg"),
            backdrop_path=FilePath("/backdrops/full.jpg"),
            genres=[Genre("Action"), Genre("Sci-Fi")],
            tmdb_id=12345,
            imdb_id="tt1234567",
        )

        saved = await repo.save(movie)

        assert saved.original_title is not None
        assert saved.original_title.value == "Original Full Movie"
        assert saved.synopsis == "A test movie with all fields."
        assert saved.poster_path is not None
        assert saved.backdrop_path is not None
        assert len(saved.genres) == 2
        assert saved.tmdb_id == 12345
        assert saved.imdb_id == "tt1234567"

    async def test_save_preserves_genres(self, db_session: AsyncSession) -> None:
        """Test that genres are correctly persisted and retrieved."""
        repo = SQLAlchemyMovieRepository(db_session)
        movie = _create_movie(
            genres=[Genre("Horror"), Genre("Thriller"), Genre("Mystery")],
        )

        await repo.save(movie)
        found = await repo.find_by_id(movie.id)  # type: ignore[arg-type]

        assert found is not None
        assert len(found.genres) == 3
        genre_values = [g.value for g in found.genres]
        assert "Horror" in genre_values
        assert "Thriller" in genre_values
        assert "Mystery" in genre_values
