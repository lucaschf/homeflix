"""Integration tests for SQLAlchemyMovieRepository."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.media.domain.entities import Movie
from src.modules.media.domain.value_objects import (
    Duration,
    FilePath,
    Genre,
    ImageUrl,
    ImdbId,
    MediaFile,
    MovieId,
    Resolution,
    Title,
    TmdbId,
    Year,
)
from src.modules.media.infrastructure.persistence.repositories import SQLAlchemyMovieRepository


def _create_movie(
    title: str = "Test Movie",
    year: int = 2024,
    duration: int = 7200,
    file_path: str = "/movies/test.mkv",
    file_size: int = 1_000_000_000,
    resolution: str = "1080p",
    movie_id: MovieId | None = None,
    **kwargs: object,
) -> Movie:
    """Create a Movie entity for testing."""
    return Movie(
        id=movie_id or MovieId.generate(),
        title=Title(title),
        year=Year(year),
        duration=Duration(duration),
        files=[
            MediaFile(
                file_path=FilePath(file_path),
                file_size=file_size,
                resolution=Resolution(resolution),
                is_primary=True,
            )
        ],
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
            files=movie.files,
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
            poster_path=ImageUrl("/posters/full.jpg"),
            backdrop_path=ImageUrl("/backdrops/full.jpg"),
            genres=[Genre("Action"), Genre("Sci-Fi")],
            tmdb_id=TmdbId(12345),
            imdb_id=ImdbId("tt1234567"),
        )

        saved = await repo.save(movie)

        assert saved.original_title is not None
        assert saved.original_title.value == "Original Full Movie"
        assert saved.synopsis == "A test movie with all fields."
        assert saved.poster_path is not None
        assert saved.backdrop_path is not None
        assert len(saved.genres) == 2
        assert saved.tmdb_id == TmdbId(12345)
        assert saved.imdb_id == ImdbId("tt1234567")

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


@pytest.mark.integration
class TestSQLAlchemyMovieRepositoryFindRandom:
    """Tests for find_random."""

    async def test_find_random_should_return_requested_limit(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemyMovieRepository(db_session)
        for i in range(5):
            await repo.save(
                _create_movie(
                    title=f"Movie {i}",
                    file_path=f"/movies/movie_{i}.mkv",
                ),
            )

        result = await repo.find_random(limit=3)

        assert len(result) == 3

    async def test_find_random_should_return_all_when_limit_exceeds_total(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemyMovieRepository(db_session)
        await repo.save(_create_movie(title="A", file_path="/movies/a.mkv"))
        await repo.save(_create_movie(title="B", file_path="/movies/b.mkv"))

        result = await repo.find_random(limit=10)

        assert len(result) == 2

    async def test_find_random_with_backdrop_should_filter_without_backdrop(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemyMovieRepository(db_session)
        await repo.save(
            _create_movie(
                title="With Backdrop",
                file_path="/movies/with.mkv",
                backdrop_path=ImageUrl("https://image.tmdb.org/backdrop.jpg"),
            ),
        )
        await repo.save(_create_movie(title="No Backdrop", file_path="/movies/no.mkv"))

        result = await repo.find_random(limit=10, with_backdrop=True)

        assert len(result) == 1
        assert result[0].title.value == "With Backdrop"

    async def test_find_random_should_exclude_deleted(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyMovieRepository(db_session)
        kept = _create_movie(title="Kept", file_path="/movies/kept.mkv")
        deleted = _create_movie(title="Deleted", file_path="/movies/deleted.mkv")
        await repo.save(kept)
        await repo.save(deleted)
        await repo.delete(deleted.id)  # type: ignore[arg-type]

        result = await repo.find_random(limit=10)

        assert len(result) == 1
        assert result[0].title.value == "Kept"


@pytest.mark.integration
class TestSQLAlchemyMovieRepositoryFindByIds:
    """Tests for find_by_ids."""

    async def test_find_by_ids_should_return_empty_dict_for_empty_input(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemyMovieRepository(db_session)

        result = await repo.find_by_ids([])

        assert result == {}

    async def test_find_by_ids_should_return_mapping_by_external_id(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemyMovieRepository(db_session)
        movie_a = _create_movie(title="A", file_path="/movies/a.mkv")
        movie_b = _create_movie(title="B", file_path="/movies/b.mkv")
        await repo.save(movie_a)
        await repo.save(movie_b)

        result = await repo.find_by_ids([movie_a.id, movie_b.id])  # type: ignore[list-item]

        assert len(result) == 2
        assert str(movie_a.id) in result
        assert str(movie_b.id) in result

    async def test_find_by_ids_should_skip_missing(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyMovieRepository(db_session)
        movie = _create_movie(title="Exists", file_path="/movies/exists.mkv")
        await repo.save(movie)
        missing_id = MovieId.generate()

        result = await repo.find_by_ids([movie.id, missing_id])  # type: ignore[list-item]

        assert len(result) == 1
        assert str(movie.id) in result

    async def test_find_by_ids_should_exclude_deleted(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyMovieRepository(db_session)
        movie = _create_movie(title="Deleted", file_path="/movies/del.mkv")
        await repo.save(movie)
        await repo.delete(movie.id)  # type: ignore[arg-type]

        result = await repo.find_by_ids([movie.id])  # type: ignore[list-item]

        assert result == {}


@pytest.mark.integration
class TestSQLAlchemyMovieRepositorySaveRestore:
    """Tests for save restoring soft-deleted records."""

    async def test_save_should_restore_soft_deleted_movie(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyMovieRepository(db_session)
        movie = _create_movie(title="Restored", file_path="/movies/r.mkv")
        await repo.save(movie)
        await repo.delete(movie.id)  # type: ignore[arg-type]

        # Re-save the same entity
        restored = await repo.save(movie)

        assert restored.id == movie.id
        found = await repo.find_by_id(movie.id)  # type: ignore[arg-type]
        assert found is not None
        assert found.title.value == "Restored"
