"""Integration tests for SQLAlchemyMovieRepository."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

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
from src.modules.media.domain.value_objects.cast_member import CastMember
from src.modules.media.infrastructure.persistence.models import MovieModel
from src.modules.media.infrastructure.persistence.repositories import SQLAlchemyMovieRepository
from src.shared_kernel.value_objects.library_id import LibraryId

_LIBRARY_ID = "lib_test12345678"
_LIBRARY_ID_OTHER = "lib_otherlibrary"


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
        library_id=_LIBRARY_ID,
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


def _id_of(movie: Movie) -> MovieId:
    """Return the movie's ID, asserting it is set (narrows the type)."""
    assert movie.id is not None
    return movie.id


async def _seed_movies(repo: SQLAlchemyMovieRepository, count: int) -> list[Movie]:
    """Save ``count`` movies with sequential titles and file paths."""
    movies = [
        _create_movie(title=f"Movie {i}", file_path=f"/movies/movie_{i}.mkv") for i in range(count)
    ]
    for movie in movies:
        await repo.save(movie)
    return movies


@pytest.mark.integration
class TestSQLAlchemyMovieRepositoryTransferFileVariantsBetweenMovies:
    async def test_moves_every_media_file_row_from_source_to_target(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        # The legacy ``movies.file_path`` column is written alongside
        # ``media_files`` rows during ``save`` and is not touched by
        # the transfer (the resolve use case soft-deletes the loser
        # immediately after, so the legacy column is unreachable in
        # production). The assertion focuses on the table this
        # method actually rewires.
        from sqlalchemy import text

        source_id: MovieId
        target_id: MovieId
        async with session_factory() as setup_session:
            repo = SQLAlchemyMovieRepository(setup_session)
            source = _create_movie(title="Loser", file_path="/movies/loser.mkv")
            target = _create_movie(title="Winner", file_path="/movies/winner.mkv")
            await repo.save(source)
            await repo.save(target)
            await setup_session.commit()
            source_id = _id_of(source)
            target_id = _id_of(target)

        async with session_factory() as transfer_session:
            transfer_repo = SQLAlchemyMovieRepository(transfer_session)
            moved = await transfer_repo.transfer_file_variants_between_movies(
                source_movie_id=source_id,
                target_movie_id=target_id,
            )
            await transfer_session.commit()
            assert moved == 1

        async with session_factory() as verify_session:
            counts = (
                await verify_session.execute(
                    text(
                        "SELECT movies.external_id, COUNT(media_files.id) "
                        "FROM movies LEFT JOIN media_files "
                        "ON media_files.movie_id = movies.id "
                        "GROUP BY movies.external_id",
                    ),
                )
            ).fetchall()
            by_ext = dict(counts)
            assert by_ext[str(source_id)] == 0
            assert by_ext[str(target_id)] == 2

    async def test_missing_source_returns_zero(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        async with session_factory() as setup_session:
            repo = SQLAlchemyMovieRepository(setup_session)
            target = _create_movie(title="Winner", file_path="/movies/winner.mkv")
            await repo.save(target)
            await setup_session.commit()
            target_id = _id_of(target)

        async with session_factory() as transfer_session:
            transfer_repo = SQLAlchemyMovieRepository(transfer_session)
            moved = await transfer_repo.transfer_file_variants_between_movies(
                source_movie_id=MovieId.generate(),
                target_movie_id=target_id,
            )
            assert moved == 0


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
            library_id=_LIBRARY_ID,
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

    async def test_find_all_by_year_returns_only_that_year(
        self,
        db_session: AsyncSession,
    ) -> None:
        """find_all_by_year filters by year and skips other years."""
        repo = SQLAlchemyMovieRepository(db_session)
        await repo.save(_create_movie(title="A", year=1997, file_path="/movies/a.mkv"))
        await repo.save(_create_movie(title="B", year=1997, file_path="/movies/b.mkv"))
        await repo.save(_create_movie(title="C", year=2001, file_path="/movies/c.mkv"))

        found = await repo.find_all_by_year(1997)

        assert sorted(m.title.value for m in found) == ["A", "B"]

    async def test_find_all_by_year_excludes_deleted(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Soft-deleted movies are not returned."""
        repo = SQLAlchemyMovieRepository(db_session)
        movie = _create_movie(title="Gone", year=1997, file_path="/movies/gone.mkv")
        await repo.save(movie)
        await repo.delete(_id_of(movie))

        assert await repo.find_all_by_year(1997) == []

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
        await _seed_movies(repo, count=5)

        result = await repo.find_random(limit=3)

        assert len(result) == 3

    async def test_find_random_should_return_all_when_limit_exceeds_total(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemyMovieRepository(db_session)
        await _seed_movies(repo, count=2)

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
        await repo.delete(_id_of(deleted))

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
        movies = await _seed_movies(repo, count=2)
        ids = [_id_of(m) for m in movies]

        result = await repo.find_by_ids(ids)

        assert len(result) == 2
        for movie_id in ids:
            assert str(movie_id) in result

    async def test_find_by_ids_should_skip_missing(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyMovieRepository(db_session)
        movie = _create_movie(title="Exists", file_path="/movies/exists.mkv")
        await repo.save(movie)

        result = await repo.find_by_ids([_id_of(movie), MovieId.generate()])

        assert len(result) == 1
        assert str(movie.id) in result

    async def test_find_by_ids_should_exclude_deleted(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyMovieRepository(db_session)
        movie = _create_movie(title="Deleted", file_path="/movies/del.mkv")
        await repo.save(movie)
        movie_id = _id_of(movie)
        await repo.delete(movie_id)

        result = await repo.find_by_ids([movie_id])

        assert result == {}


@pytest.mark.integration
class TestSQLAlchemyMovieRepositoryFindByTmdbIds:
    """Tests for ``find_by_tmdb_ids`` — used by ``GetRelatedMovies``."""

    async def test_returns_empty_dict_for_empty_input(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyMovieRepository(db_session)
        assert await repo.find_by_tmdb_ids([]) == {}

    async def test_returns_mapping_by_tmdb_id(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyMovieRepository(db_session)
        a = _create_movie(title="A", file_path="/movies/a.mkv", tmdb_id=TmdbId(100))
        b = _create_movie(title="B", file_path="/movies/b.mkv", tmdb_id=TmdbId(200))
        await repo.save(a)
        await repo.save(b)

        result = await repo.find_by_tmdb_ids([100, 200])

        assert set(result.keys()) == {100, 200}
        assert result[100].title.value == "A"
        assert result[200].title.value == "B"

    async def test_skips_ids_not_in_catalog(self, db_session: AsyncSession) -> None:
        # Mirrors how the real flow works: TMDB recommendations include
        # titles the user doesn't have; the use case relies on missing
        # ids simply not appearing in the result.
        repo = SQLAlchemyMovieRepository(db_session)
        present = _create_movie(
            title="Present",
            file_path="/movies/p.mkv",
            tmdb_id=TmdbId(42),
        )
        await repo.save(present)

        result = await repo.find_by_tmdb_ids([42, 9999])

        assert set(result.keys()) == {42}

    async def test_excludes_soft_deleted(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyMovieRepository(db_session)
        movie = _create_movie(
            title="Trashed",
            file_path="/movies/trashed.mkv",
            tmdb_id=TmdbId(7),
        )
        await repo.save(movie)
        await repo.delete(_id_of(movie))

        assert await repo.find_by_tmdb_ids([7]) == {}

    async def test_skips_movies_with_null_tmdb_id(self, db_session: AsyncSession) -> None:
        # Defensive: the SQL filter is ``tmdb_id IN (...)`` but movies
        # without a ``tmdb_id`` shouldn't appear under any key, even
        # if a ``None`` somehow leaks through.
        repo = SQLAlchemyMovieRepository(db_session)
        no_tmdb = _create_movie(title="Manual", file_path="/movies/manual.mkv")
        await repo.save(no_tmdb)

        assert await repo.find_by_tmdb_ids([1, 2, 3]) == {}


@pytest.mark.integration
class TestSQLAlchemyMovieRepositorySaveRestore:
    """Tests for save restoring soft-deleted records."""

    async def test_save_should_restore_soft_deleted_movie(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyMovieRepository(db_session)
        movie = _create_movie(title="Restored", file_path="/movies/r.mkv")
        await repo.save(movie)
        movie_id = _id_of(movie)
        await repo.delete(movie_id)

        # Re-save the same entity
        restored = await repo.save(movie)

        assert restored.id == movie.id
        found = await repo.find_by_id(movie_id)
        assert found is not None
        assert found.title.value == "Restored"


@pytest.mark.integration
class TestSQLAlchemyMovieRepositoryListPaginated:
    """Integration tests for the cursor-paginated listing."""

    async def test_should_return_first_page_when_cursor_is_none(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemyMovieRepository(db_session)
        await _seed_movies(repo, 5)

        page = await repo.list_paginated(cursor=None, limit=3)

        assert len(page.items) == 3
        assert page.pagination.has_more is True
        assert page.pagination.next_cursor is not None
        assert page.total_count is None  # include_total defaults to False

    async def test_should_walk_to_the_next_page_via_cursor(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyMovieRepository(db_session)
        await _seed_movies(repo, 5)

        page1 = await repo.list_paginated(cursor=None, limit=2)
        page2 = await repo.list_paginated(cursor=page1.pagination.next_cursor, limit=2)
        page3 = await repo.list_paginated(cursor=page2.pagination.next_cursor, limit=2)

        page1_ids = {_id_of(m) for m in page1.items}
        page2_ids = {_id_of(m) for m in page2.items}
        page3_ids = {_id_of(m) for m in page3.items}

        # No overlap between consecutive pages — the cursor must be exclusive
        assert page1_ids.isdisjoint(page2_ids)
        assert page2_ids.isdisjoint(page3_ids)
        # Five rows total, walked in 2-2-1
        assert len(page1.items) == 2
        assert len(page2.items) == 2
        assert len(page3.items) == 1
        assert page3.pagination.has_more is False
        assert page3.pagination.next_cursor is None

    async def test_should_return_has_more_false_when_exact_fit(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemyMovieRepository(db_session)
        await _seed_movies(repo, 3)

        # Asking for exactly the number of rows that exist must NOT
        # report has_more — the N+1 fetch comes back with N rows so
        # the +1 sentinel never appears.
        page = await repo.list_paginated(cursor=None, limit=3)

        assert len(page.items) == 3
        assert page.pagination.has_more is False
        assert page.pagination.next_cursor is None

    async def test_should_return_empty_page_when_no_movies(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyMovieRepository(db_session)

        page = await repo.list_paginated(cursor=None, limit=20)

        assert page.items == []
        assert page.pagination.has_more is False
        assert page.pagination.next_cursor is None

    async def test_should_silently_fall_back_to_first_page_on_invalid_cursor(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemyMovieRepository(db_session)
        await _seed_movies(repo, 3)

        page = await repo.list_paginated(cursor="not-a-valid-cursor", limit=10)

        assert len(page.items) == 3

    async def test_should_order_by_id_desc(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyMovieRepository(db_session)
        # Saving movies sequentially gives them monotonically increasing
        # internal ids — the test asserts the most recently saved row
        # comes first, which is the contract of the cursor sort.
        seeded = await _seed_movies(repo, 4)

        page = await repo.list_paginated(cursor=None, limit=4)

        returned_titles = [m.title.value for m in page.items]
        seeded_titles = [m.title.value for m in seeded]
        assert returned_titles == list(reversed(seeded_titles))

    async def test_should_exclude_soft_deleted_movies(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyMovieRepository(db_session)
        movies = await _seed_movies(repo, 3)
        await repo.delete(_id_of(movies[0]))

        page = await repo.list_paginated(cursor=None, limit=10)

        assert len(page.items) == 2
        returned_ids = {_id_of(m) for m in page.items}
        assert _id_of(movies[0]) not in returned_ids

    async def test_should_populate_total_count_when_requested(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemyMovieRepository(db_session)
        await _seed_movies(repo, 7)

        page = await repo.list_paginated(cursor=None, limit=3, include_total=True)

        assert page.total_count == 7
        assert len(page.items) == 3
        assert page.pagination.has_more is True

    async def test_should_not_count_soft_deleted_in_total(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyMovieRepository(db_session)
        movies = await _seed_movies(repo, 5)
        await repo.delete(_id_of(movies[0]))
        await repo.delete(_id_of(movies[1]))

        page = await repo.list_paginated(cursor=None, limit=10, include_total=True)

        assert page.total_count == 3


@pytest.mark.integration
class TestSQLAlchemyMovieRepositoryListPaginatedAdminFilters:
    """Integration coverage for the admin Catalog filter set on
    ``list_paginated`` — library_id, has_tmdb_id, needs_enrichment_review."""

    async def test_library_id_should_restrict_to_a_single_library(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemyMovieRepository(db_session)
        await repo.save(_create_movie(title="A", file_path="/m/a.mkv"))
        await repo.save(
            _movie_in_library(library_id=_LIBRARY_ID_OTHER, title="B", file_path="/m/b.mkv")
        )

        page = await repo.list_paginated(cursor=None, limit=10, library_id=_LIBRARY_ID)

        assert {m.title.value for m in page.items} == {"A"}

    async def test_has_tmdb_id_true_should_keep_only_enriched_rows(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemyMovieRepository(db_session)
        await repo.save(_create_movie(title="Plain", file_path="/m/p.mkv"))
        await repo.save(
            _create_movie(title="Enriched", file_path="/m/e.mkv").with_updates(tmdb_id=TmdbId(550))
        )

        page = await repo.list_paginated(cursor=None, limit=10, has_tmdb_id=True)

        assert {m.title.value for m in page.items} == {"Enriched"}

    async def test_has_tmdb_id_false_should_keep_only_unenriched_rows(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemyMovieRepository(db_session)
        await repo.save(_create_movie(title="Plain", file_path="/m/p.mkv"))
        await repo.save(
            _create_movie(title="Enriched", file_path="/m/e.mkv").with_updates(tmdb_id=TmdbId(550))
        )

        page = await repo.list_paginated(cursor=None, limit=10, has_tmdb_id=False)

        assert {m.title.value for m in page.items} == {"Plain"}

    async def test_needs_enrichment_review_should_keep_flagged_rows(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemyMovieRepository(db_session)
        await repo.save(_create_movie(title="Clean", file_path="/m/c.mkv"))
        await repo.save(
            _create_movie(title="Flagged", file_path="/m/f.mkv").with_updates(
                needs_enrichment_review=True
            )
        )

        page = await repo.list_paginated(cursor=None, limit=10, needs_enrichment_review=True)

        assert {m.title.value for m in page.items} == {"Flagged"}

    async def test_filters_should_compose(self, db_session: AsyncSession) -> None:
        """Multiple filters combine via AND — a row must satisfy every
        constraint to land in the page."""
        repo = SQLAlchemyMovieRepository(db_session)
        await repo.save(
            _create_movie(title="Match", file_path="/m/match.mkv").with_updates(
                needs_enrichment_review=True
            )
        )
        await repo.save(
            _create_movie(title="WrongFlag", file_path="/m/wf.mkv").with_updates(tmdb_id=TmdbId(99))
        )

        page = await repo.list_paginated(
            cursor=None,
            limit=10,
            has_tmdb_id=False,
            needs_enrichment_review=True,
        )

        assert {m.title.value for m in page.items} == {"Match"}

    async def test_q_blank_should_short_circuit_the_fts_round_trip(
        self, db_session: AsyncSession
    ) -> None:
        """Empty / whitespace-only ``q`` skips the FTS5 lookup so the
        regular ``id DESC`` page still lands every non-deleted row.

        End-to-end coverage for the FTS5 hit path lives in the
        ``/api/v1/movies?q=...`` smoke flow — the in-memory SQLite
        test database doesn't have the ``movies_fts`` virtual table
        (it ships via Alembic, not ``Base.metadata.create_all``)
        and bootstrapping it here would duplicate the chain of
        migrations that build the localized JSON projections."""
        repo = SQLAlchemyMovieRepository(db_session)
        await repo.save(_create_movie(title="A", file_path="/m/a.mkv"))
        await repo.save(_create_movie(title="B", file_path="/m/b.mkv"))

        page = await repo.list_paginated(cursor=None, limit=10, q="   ")

        assert {m.title.value for m in page.items} == {"A", "B"}


@pytest.mark.integration
class TestSQLAlchemyMovieRepositoryListRecentlyAdded:
    """Integration tests for the bounded "top N newest" projection."""

    async def test_should_return_movies_in_id_desc_order(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyMovieRepository(db_session)
        seeded = await _seed_movies(repo, 4)

        result = await repo.list_recently_added(limit=10)

        returned_titles = [m.title.value for m in result]
        assert returned_titles == list(reversed([m.title.value for m in seeded]))

    async def test_should_clamp_to_limit(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyMovieRepository(db_session)
        await _seed_movies(repo, 5)

        result = await repo.list_recently_added(limit=3)

        assert len(result) == 3

    async def test_should_return_all_when_limit_exceeds_total(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemyMovieRepository(db_session)
        await _seed_movies(repo, 2)

        result = await repo.list_recently_added(limit=10)

        assert len(result) == 2

    async def test_should_exclude_soft_deleted(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyMovieRepository(db_session)
        movies = await _seed_movies(repo, 3)
        await repo.delete(_id_of(movies[-1]))

        result = await repo.list_recently_added(limit=10)

        returned_ids = {_id_of(m) for m in result}
        assert _id_of(movies[-1]) not in returned_ids
        assert len(result) == 2

    async def test_should_return_empty_when_no_movies(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyMovieRepository(db_session)

        result = await repo.list_recently_added(limit=10)

        assert list(result) == []


@pytest.mark.integration
class TestSQLAlchemyMovieRepositoryListGenreRows:
    """Integration tests for the lightweight genre projection."""

    async def test_should_return_one_row_per_movie(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyMovieRepository(db_session)
        await repo.save(_create_movie(title="A", file_path="/m/a.mkv").with_genre(Genre("Action")))
        await repo.save(_create_movie(title="B", file_path="/m/b.mkv").with_genre(Genre("Comedy")))

        rows = await repo.list_genre_rows(lang="en")

        assert len(rows) == 2

    async def test_should_split_comma_separated_genres(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyMovieRepository(db_session)
        movie = (
            _create_movie(title="A", file_path="/m/a.mkv")
            .with_genre(Genre("Action"))
            .with_genre(Genre("Comedy"))
            .with_genre(Genre("Drama"))
        )
        await repo.save(movie)

        rows = await repo.list_genre_rows(lang="en")

        assert rows[0].canonical_genres == ["Action", "Comedy", "Drama"]

    async def test_should_skip_rows_with_no_genres(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyMovieRepository(db_session)
        # One movie with a genre, one without
        await repo.save(_create_movie(title="A", file_path="/m/a.mkv").with_genre(Genre("Action")))
        await repo.save(_create_movie(title="B", file_path="/m/b.mkv"))

        rows = await repo.list_genre_rows(lang="en")

        # Only the movie with a genre is returned — repo filters
        # `genres IS NOT NULL` so the empty one is excluded.
        assert len(rows) == 1

    async def test_should_exclude_soft_deleted(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyMovieRepository(db_session)
        m1 = _create_movie(title="A", file_path="/m/a.mkv").with_genre(Genre("Action"))
        m2 = _create_movie(title="B", file_path="/m/b.mkv").with_genre(Genre("Comedy"))
        await repo.save(m1)
        await repo.save(m2)
        await repo.delete(_id_of(m1))

        rows = await repo.list_genre_rows(lang="en")

        assert len(rows) == 1
        assert rows[0].canonical_genres == ["Comedy"]


@pytest.mark.integration
class TestSQLAlchemyMovieRepositoryListPaginatedByGenre:
    """Integration tests for the title-sorted, genre-filtered listing."""

    async def test_should_filter_to_movies_with_the_given_genre(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemyMovieRepository(db_session)
        await repo.save(
            _create_movie(title="Avatar", file_path="/m/a.mkv").with_genre(Genre("Action"))
        )
        await repo.save(
            _create_movie(title="Comedy Show", file_path="/m/c.mkv").with_genre(Genre("Comedy"))
        )

        page = await repo.list_paginated_by_genre(genre=Genre("Action"), cursor=None, limit=10)

        assert len(page.items) == 1
        assert page.items[0].title.value == "Avatar"

    async def test_should_not_match_substrings_or_partial_words(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemyMovieRepository(db_session)
        # `Reaction` must NOT match `Action`, and neither should
        # `Action Adventure`.
        await repo.save(
            _create_movie(title="Real", file_path="/m/real.mkv").with_genre(Genre("Reaction"))
        )
        await repo.save(
            _create_movie(title="Adv", file_path="/m/adv.mkv").with_genre(Genre("Action Adventure"))
        )
        await repo.save(
            _create_movie(title="True", file_path="/m/true.mkv").with_genre(Genre("Action"))
        )

        page = await repo.list_paginated_by_genre(genre=Genre("Action"), cursor=None, limit=10)

        assert len(page.items) == 1
        assert page.items[0].title.value == "True"

    async def test_should_sort_alphabetically_case_insensitive(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemyMovieRepository(db_session)
        for title in ["zebra", "Apple", "mango", "Banana"]:
            await repo.save(
                _create_movie(title=title, file_path=f"/m/{title.lower()}.mkv").with_genre(
                    Genre("Action")
                )
            )

        page = await repo.list_paginated_by_genre(genre=Genre("Action"), cursor=None, limit=10)

        titles = [m.title.value for m in page.items]
        assert titles == ["Apple", "Banana", "mango", "zebra"]

    async def test_should_walk_pages_via_cursor(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyMovieRepository(db_session)
        for title in ["Alpha", "Beta", "Gamma", "Delta", "Epsilon"]:
            await repo.save(
                _create_movie(title=title, file_path=f"/m/{title}.mkv").with_genre(Genre("Action"))
            )

        page1 = await repo.list_paginated_by_genre(genre=Genre("Action"), cursor=None, limit=2)
        page2 = await repo.list_paginated_by_genre(
            genre=Genre("Action"),
            cursor=page1.pagination.next_cursor,
            limit=2,
        )
        page3 = await repo.list_paginated_by_genre(
            genre=Genre("Action"),
            cursor=page2.pagination.next_cursor,
            limit=2,
        )

        all_titles = (
            [m.title.value for m in page1.items]
            + [m.title.value for m in page2.items]
            + [m.title.value for m in page3.items]
        )
        # All five titles in alphabetical order, no overlap
        assert all_titles == ["Alpha", "Beta", "Delta", "Epsilon", "Gamma"]
        assert page3.pagination.has_more is False

    async def test_should_populate_per_item_cursors(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyMovieRepository(db_session)
        for title in ["Alpha", "Beta", "Gamma"]:
            await repo.save(
                _create_movie(title=title, file_path=f"/m/{title}.mkv").with_genre(Genre("Action"))
            )

        page = await repo.list_paginated_by_genre(genre=Genre("Action"), cursor=None, limit=10)

        # Per-item cursors are needed by the catalog by-genre use
        # case to advance partial-prefix consumption.
        assert page.item_cursors is not None
        assert len(page.item_cursors) == len(page.items) == 3

    async def test_should_resume_correctly_when_titles_share_prefix(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemyMovieRepository(db_session)
        # Three movies with the same title — the cursor's id
        # tie-breaker must keep them all visible across pages.
        for path in ["/m/a1.mkv", "/m/a2.mkv", "/m/a3.mkv"]:
            await repo.save(_create_movie(title="Same", file_path=path).with_genre(Genre("Action")))

        page1 = await repo.list_paginated_by_genre(genre=Genre("Action"), cursor=None, limit=2)
        page2 = await repo.list_paginated_by_genre(
            genre=Genre("Action"),
            cursor=page1.pagination.next_cursor,
            limit=2,
        )

        assert len(page1.items) == 2
        assert len(page2.items) == 1
        assert page2.pagination.has_more is False

    async def test_should_exclude_soft_deleted(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyMovieRepository(db_session)
        m1 = _create_movie(title="A", file_path="/m/a.mkv").with_genre(Genre("Action"))
        m2 = _create_movie(title="B", file_path="/m/b.mkv").with_genre(Genre("Action"))
        await repo.save(m1)
        await repo.save(m2)
        await repo.delete(_id_of(m1))

        page = await repo.list_paginated_by_genre(genre=Genre("Action"), cursor=None, limit=10)

        assert len(page.items) == 1
        assert page.items[0].title.value == "B"


@pytest.mark.integration
class TestSQLAlchemyMovieRepositoryListPaginatedByCastMember:
    """Integration tests for the title-sorted, cast-filtered listing."""

    async def test_should_filter_to_movies_with_the_actor(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyMovieRepository(db_session)
        weaver = [CastMember(name="Sigourney Weaver")]
        other = [CastMember(name="Tom Hanks")]
        await repo.save(
            _create_movie(title="Alien", file_path="/m/alien.mkv").with_updates(cast=weaver)
        )
        await repo.save(
            _create_movie(title="Forrest Gump", file_path="/m/fg.mkv").with_updates(cast=other)
        )

        page = await repo.list_paginated_by_cast_member(
            actor_name="Sigourney Weaver", cursor=None, limit=10
        )

        assert len(page.items) == 1
        assert page.items[0].title.value == "Alien"

    async def test_should_match_by_exact_name_not_substring(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyMovieRepository(db_session)
        # "Tom Hanks" must NOT match "Tom Hanks Jr." — the closing
        # quote of the JSON-encoded needle prevents prefix matches.
        await repo.save(
            _create_movie(title="Other", file_path="/m/o.mkv").with_updates(
                cast=[CastMember(name="Tom Hanks Jr.")]
            )
        )
        await repo.save(
            _create_movie(title="Forrest Gump", file_path="/m/fg.mkv").with_updates(
                cast=[CastMember(name="Tom Hanks")]
            )
        )

        page = await repo.list_paginated_by_cast_member(
            actor_name="Tom Hanks", cursor=None, limit=10
        )

        assert len(page.items) == 1
        assert page.items[0].title.value == "Forrest Gump"

    async def test_should_handle_special_characters_in_name(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyMovieRepository(db_session)
        # Apostrophe + accents must round-trip through JSON encoding
        # and the LIKE filter correctly.
        await repo.save(
            _create_movie(title="Hidden Figures", file_path="/m/hf.mkv").with_updates(
                cast=[CastMember(name="Taraji P. Henson")]
            )
        )
        await repo.save(
            _create_movie(title="Cast Away", file_path="/m/ca.mkv").with_updates(
                cast=[CastMember(name="Wilson O'Brien")]
            )
        )

        page = await repo.list_paginated_by_cast_member(
            actor_name="Wilson O'Brien", cursor=None, limit=10
        )

        assert len(page.items) == 1
        assert page.items[0].title.value == "Cast Away"

    async def test_should_sort_alphabetically_case_insensitive(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemyMovieRepository(db_session)
        weaver = [CastMember(name="Sigourney Weaver")]
        for title in ["zebra", "Apple", "mango", "Banana"]:
            await repo.save(
                _create_movie(title=title, file_path=f"/m/{title.lower()}.mkv").with_updates(
                    cast=weaver
                )
            )

        page = await repo.list_paginated_by_cast_member(
            actor_name="Sigourney Weaver", cursor=None, limit=10
        )

        titles = [m.title.value for m in page.items]
        assert titles == ["Apple", "Banana", "mango", "zebra"]

    async def test_should_walk_pages_via_cursor(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyMovieRepository(db_session)
        weaver = [CastMember(name="Sigourney Weaver")]
        for title in ["Alpha", "Beta", "Gamma", "Delta", "Epsilon"]:
            await repo.save(
                _create_movie(title=title, file_path=f"/m/{title}.mkv").with_updates(cast=weaver)
            )

        page1 = await repo.list_paginated_by_cast_member(
            actor_name="Sigourney Weaver", cursor=None, limit=2
        )
        page2 = await repo.list_paginated_by_cast_member(
            actor_name="Sigourney Weaver",
            cursor=page1.pagination.next_cursor,
            limit=2,
        )
        page3 = await repo.list_paginated_by_cast_member(
            actor_name="Sigourney Weaver",
            cursor=page2.pagination.next_cursor,
            limit=2,
        )

        all_titles = (
            [m.title.value for m in page1.items]
            + [m.title.value for m in page2.items]
            + [m.title.value for m in page3.items]
        )
        assert all_titles == ["Alpha", "Beta", "Delta", "Epsilon", "Gamma"]
        assert page3.pagination.has_more is False

    async def test_should_exclude_soft_deleted(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyMovieRepository(db_session)
        weaver = [CastMember(name="Sigourney Weaver")]
        m1 = _create_movie(title="A", file_path="/m/a.mkv").with_updates(cast=weaver)
        m2 = _create_movie(title="B", file_path="/m/b.mkv").with_updates(cast=weaver)
        await repo.save(m1)
        await repo.save(m2)
        await repo.delete(_id_of(m1))

        page = await repo.list_paginated_by_cast_member(
            actor_name="Sigourney Weaver", cursor=None, limit=10
        )

        assert len(page.items) == 1
        assert page.items[0].title.value == "B"

    async def test_should_return_empty_when_no_match(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyMovieRepository(db_session)
        await repo.save(
            _create_movie(title="A", file_path="/m/a.mkv").with_updates(
                cast=[CastMember(name="Someone Else")]
            )
        )

        page = await repo.list_paginated_by_cast_member(
            actor_name="Nobody Famous", cursor=None, limit=10
        )

        assert page.items == []
        assert page.pagination.has_more is False


@pytest.mark.integration
class TestCountUnderPaths:
    """Integration tests for ``count_under_paths``."""

    async def test_returns_zero_for_empty_paths(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyMovieRepository(db_session)
        await repo.save(_create_movie(file_path="/media/movies/a.mkv"))

        assert await repo.count_under_paths([]) == 0

    async def test_matches_posix_prefix(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyMovieRepository(db_session)
        await repo.save(_create_movie(title="A", file_path="/media/movies/a.mkv"))
        await repo.save(_create_movie(title="B", file_path="/media/movies/nested/b.mkv"))
        await repo.save(_create_movie(title="Other", file_path="/elsewhere/c.mkv"))

        assert await repo.count_under_paths(["/media/movies"]) == 2

    async def test_matches_windows_prefix(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyMovieRepository(db_session)
        await repo.save(_create_movie(title="W1", file_path=r"D:\homeflix\movie1.mkv"))
        await repo.save(_create_movie(title="W2", file_path=r"D:\homeflix\sub\movie2.mkv"))
        await repo.save(_create_movie(title="Other", file_path=r"E:\other\x.mkv"))

        assert await repo.count_under_paths([r"D:\homeflix"]) == 2

    async def test_sums_across_multiple_libraries(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyMovieRepository(db_session)
        await repo.save(_create_movie(title="A", file_path="/a/one.mkv"))
        await repo.save(_create_movie(title="B", file_path="/b/two.mkv"))
        await repo.save(_create_movie(title="C", file_path="/c/three.mkv"))

        assert await repo.count_under_paths(["/a", "/b"]) == 2

    async def test_does_not_match_sibling_directory(self, db_session: AsyncSession) -> None:
        """``/media/movies`` must not swallow ``/media/movies-extra``."""
        repo = SQLAlchemyMovieRepository(db_session)
        await repo.save(_create_movie(title="A", file_path="/media/movies/a.mkv"))
        await repo.save(_create_movie(title="Sibling", file_path="/media/movies-extra/b.mkv"))

        assert await repo.count_under_paths(["/media/movies"]) == 1

    async def test_excludes_soft_deleted(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyMovieRepository(db_session)
        a = _create_movie(title="A", file_path="/media/a.mkv")
        b = _create_movie(title="B", file_path="/media/b.mkv")
        await repo.save(a)
        await repo.save(b)
        await repo.delete(_id_of(a))

        assert await repo.count_under_paths(["/media"]) == 1

    async def test_normalizes_trailing_posix_separator(self, db_session: AsyncSession) -> None:
        """A trailing ``/`` on the filter path must still match stored rows."""
        repo = SQLAlchemyMovieRepository(db_session)
        await repo.save(_create_movie(title="A", file_path="/media/movies/a.mkv"))
        await repo.save(_create_movie(title="Sibling", file_path="/media/movies-extra/b.mkv"))

        assert await repo.count_under_paths(["/media/movies/"]) == 1

    async def test_normalizes_trailing_windows_separator(self, db_session: AsyncSession) -> None:
        """Mirror the POSIX sibling check for the Windows variant."""
        repo = SQLAlchemyMovieRepository(db_session)
        await repo.save(_create_movie(title="W", file_path=r"D:\homeflix\movie1.mkv"))
        await repo.save(_create_movie(title="Sibling", file_path=r"D:\homeflix-extra\movie2.mkv"))

        assert await repo.count_under_paths([r"D:\homeflix" + "\\"]) == 1

    async def test_matches_posix_root_path(self, db_session: AsyncSession) -> None:
        """A library rooted at ``/`` must match every stored POSIX path.

        Without special handling ``rstrip`` collapses ``/`` to the empty
        string and the filter is dropped entirely, so this guards against
        the regression.
        """
        repo = SQLAlchemyMovieRepository(db_session)
        await repo.save(_create_movie(title="A", file_path="/media/a.mkv"))
        await repo.save(_create_movie(title="B", file_path="/other/b.mkv"))

        assert await repo.count_under_paths(["/"]) == 2


@pytest.mark.integration
class TestSQLAlchemyMovieRepositoryCount:
    """Integration tests for the catalog-wide ``count`` method."""

    async def test_should_return_zero_for_empty_catalog(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyMovieRepository(db_session)
        assert await repo.count() == 0

    async def test_should_count_every_non_deleted_movie(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyMovieRepository(db_session)
        await repo.save(_create_movie(title="A", file_path="/a.mkv"))
        await repo.save(_create_movie(title="B", file_path="/b.mkv"))
        await repo.save(_create_movie(title="C", file_path="/c.mkv"))

        assert await repo.count() == 3

    async def test_should_exclude_soft_deleted(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyMovieRepository(db_session)
        a = _create_movie(title="A", file_path="/a.mkv")
        b = _create_movie(title="B", file_path="/b.mkv")
        await repo.save(a)
        await repo.save(b)
        await repo.delete(_id_of(b))

        assert await repo.count() == 1


@pytest.mark.integration
class TestSQLAlchemyMovieRepositoryLibraryIsolation:
    """Cross-library isolation at the persistence layer.

    The repository doesn't filter by ``library_id`` itself yet — that's
    a higher-layer responsibility wired in PR 6b — but the column has
    to persist accurately so a manual filter never leaks rows across
    libraries. Mirrors the cross-key isolation tests in
    ``tests/modules/watch_progress/integration/persistence/repositories/``.
    """

    async def test_two_libraries_can_coexist_and_be_filtered_by_column(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemyMovieRepository(db_session)

        # Library A: two movies
        await repo.save(_create_movie(title="A1", file_path="/libA/m1.mkv"))
        await repo.save(_create_movie(title="A2", file_path="/libA/m2.mkv"))

        # Library B (different library_id): one movie
        movie_b = Movie(
            library_id=_LIBRARY_ID_OTHER,
            id=MovieId.generate(),
            title=Title("B1"),
            year=Year(2024),
            duration=Duration(7200),
            files=[
                MediaFile(
                    file_path=FilePath("/libB/m1.mkv"),
                    file_size=1_000_000_000,
                    resolution=Resolution("1080p"),
                    is_primary=True,
                )
            ],
        )
        await repo.save(movie_b)

        # Direct queries by library_id never leak across.
        rows_a = (
            (
                await db_session.execute(
                    select(MovieModel).where(MovieModel.library_id == _LIBRARY_ID)
                )
            )
            .scalars()
            .all()
        )
        rows_b = (
            (
                await db_session.execute(
                    select(MovieModel).where(MovieModel.library_id == _LIBRARY_ID_OTHER)
                )
            )
            .scalars()
            .all()
        )

        assert {r.title for r in rows_a} == {"A1", "A2"}
        assert {r.title for r in rows_b} == {"B1"}
        assert all(r.library_id == _LIBRARY_ID for r in rows_a)
        assert all(r.library_id == _LIBRARY_ID_OTHER for r in rows_b)

    async def test_library_id_persists_through_save_and_reload(
        self, db_session: AsyncSession
    ) -> None:
        """``library_id`` round-trips through save + find_by_id."""
        repo = SQLAlchemyMovieRepository(db_session)
        movie = _create_movie(title="Scoped", file_path="/libA/scoped.mkv")

        await repo.save(movie)
        assert movie.id is not None
        found = await repo.find_by_id(movie.id)

        assert found is not None
        assert found.library_id == _LIBRARY_ID


def _movie_in_library(*, library_id: str, title: str, file_path: str) -> Movie:
    """Build a Movie with an explicit ``library_id`` for ACL tests."""
    return Movie(
        library_id=library_id,
        id=MovieId.generate(),
        title=Title(title),
        year=Year(2024),
        duration=Duration(7200),
        files=[
            MediaFile(
                file_path=FilePath(file_path),
                file_size=1_000_000_000,
                resolution=Resolution("1080p"),
                is_primary=True,
            )
        ],
    )


@pytest.mark.integration
class TestAllowedLibraryIdsFilter:
    """``allowed_library_ids`` kwarg restricts reads to a set of libraries.

    The use cases pass the caller's profile ACL as this kwarg; these
    tests pin the SQL filter at the repository boundary. Two
    representative methods are covered: ``list_paginated`` (the page
    query that backs the catalog grid) and ``find_by_id`` (the lookup
    that backs the detail page and the stream routes).
    """

    async def test_list_paginated_includes_only_allowed_libraries(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemyMovieRepository(db_session)
        await repo.save(
            _movie_in_library(library_id=_LIBRARY_ID, title="Visible", file_path="/libA/v.mkv")
        )
        await repo.save(
            _movie_in_library(
                library_id=_LIBRARY_ID_OTHER,
                title="Hidden",
                file_path="/libB/h.mkv",
            )
        )

        page = await repo.list_paginated(
            cursor=None,
            limit=10,
            allowed_library_ids=[LibraryId(_LIBRARY_ID)],
        )

        titles = {m.title.value for m in page.items}
        assert titles == {"Visible"}
        assert "Hidden" not in titles

    async def test_list_paginated_excludes_libraries_outside_allowed_set(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemyMovieRepository(db_session)
        await repo.save(
            _movie_in_library(library_id=_LIBRARY_ID, title="In A", file_path="/libA/in.mkv")
        )
        await repo.save(
            _movie_in_library(
                library_id=_LIBRARY_ID_OTHER,
                title="In B",
                file_path="/libB/in.mkv",
            )
        )

        # Allowed = library B only.
        page = await repo.list_paginated(
            cursor=None,
            limit=10,
            allowed_library_ids=[LibraryId(_LIBRARY_ID_OTHER)],
        )

        titles = {m.title.value for m in page.items}
        assert titles == {"In B"}

    async def test_find_by_id_returns_none_for_row_outside_acl(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemyMovieRepository(db_session)
        movie = _movie_in_library(
            library_id=_LIBRARY_ID_OTHER,
            title="Forbidden",
            file_path="/libB/forbidden.mkv",
        )
        await repo.save(movie)
        assert movie.id is not None

        # Caller is restricted to library A — must NOT see the row.
        found = await repo.find_by_id(movie.id, allowed_library_ids=[LibraryId(_LIBRARY_ID)])

        assert found is None

    async def test_find_by_id_returns_row_when_inside_acl(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyMovieRepository(db_session)
        movie = _movie_in_library(
            library_id=_LIBRARY_ID, title="Allowed", file_path="/libA/allowed.mkv"
        )
        await repo.save(movie)
        assert movie.id is not None

        found = await repo.find_by_id(movie.id, allowed_library_ids=[LibraryId(_LIBRARY_ID)])

        assert found is not None
        assert found.title.value == "Allowed"


class TestFindNeedsEnrichmentReview:
    """Tests for ``find_needs_enrichment_review`` — admin review queue."""

    async def test_should_return_only_flagged_movies(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyMovieRepository(db_session)
        flagged = _create_movie(
            title="Salem's Lot",
            file_path="/movies/salem.mkv",
            needs_enrichment_review=True,
        )
        clean = _create_movie(title="Inception", file_path="/movies/inception.mkv")
        await repo.save(flagged)
        await repo.save(clean)

        result = await repo.find_needs_enrichment_review()

        assert [m.title.value for m in result] == ["Salem's Lot"]

    async def test_should_return_empty_when_none_flagged(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyMovieRepository(db_session)
        await repo.save(_create_movie(title="Inception", file_path="/movies/inception.mkv"))

        result = await repo.find_needs_enrichment_review()

        assert result == []

    async def test_should_exclude_soft_deleted_rows(self, db_session: AsyncSession) -> None:
        """Admin queue shouldn't surface rows the operator already
        soft-deleted — they're conceptually gone."""
        repo = SQLAlchemyMovieRepository(db_session)
        movie = _create_movie(
            title="Salem's Lot",
            file_path="/movies/salem.mkv",
            needs_enrichment_review=True,
        )
        await repo.save(movie)
        assert movie.id is not None
        await repo.delete(movie.id)

        result = await repo.find_needs_enrichment_review()

        assert result == []
