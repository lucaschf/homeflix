"""Integration tests for SQLAlchemySeriesRepository."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.media.domain.entities import Episode, Season, Series
from src.modules.media.domain.value_objects import (
    Duration,
    EpisodeId,
    FilePath,
    Genre,
    ImageUrl,
    ImdbId,
    IntroDetectionState,
    IntroMarker,
    IntroMarkerSource,
    MediaFile,
    Resolution,
    SeasonId,
    SeasonNumber,
    SeriesId,
    Title,
    TmdbId,
    Year,
)
from src.modules.media.infrastructure.persistence.models import SeriesModel
from src.modules.media.infrastructure.persistence.repositories import SQLAlchemySeriesRepository

_LIBRARY_ID = "lib_test12345678"
_LIBRARY_ID_OTHER = "lib_otherlibrary"


def _create_episode(
    series_id: SeriesId,
    season_number: int = 1,
    episode_number: int = 1,
    title: str = "Test Episode",
    duration: int = 2700,
    file_path: str | None = None,
) -> Episode:
    """Create an Episode entity for testing."""
    path = file_path or f"/series/s{season_number:02d}e{episode_number:02d}.mkv"
    return Episode(
        id=EpisodeId.generate(),
        series_id=series_id,
        season_number=season_number,
        episode_number=episode_number,
        title=Title(title),
        duration=Duration(duration),
        files=[
            MediaFile(
                file_path=FilePath(path),
                file_size=500_000_000,
                resolution=Resolution("1080p"),
                is_primary=True,
            )
        ],
    )


def _create_season(
    series_id: SeriesId,
    season_number: int = 1,
    episode_count: int = 0,
) -> Season:
    """Create a Season entity for testing."""
    episodes = [_create_episode(series_id, season_number, i + 1) for i in range(episode_count)]
    return Season(
        id=SeasonId.generate(),
        series_id=series_id,
        season_number=season_number,
        title=Title(f"Season {season_number}"),
        episodes=episodes,
    )


def _create_series(
    title: str = "Test Series",
    start_year: int = 2020,
    season_count: int = 0,
    episodes_per_season: int = 0,
    series_id: SeriesId | None = None,
    **kwargs: object,
) -> Series:
    """Create a Series entity for testing."""
    sid = series_id or SeriesId.generate()
    seasons = [_create_season(sid, i + 1, episodes_per_season) for i in range(season_count)]
    return Series(
        library_id=_LIBRARY_ID,
        id=sid,
        title=Title(title),
        start_year=Year(start_year),
        seasons=seasons,
        **kwargs,
    )


def _id_of(series: Series) -> SeriesId:
    """Return the series' ID, asserting it is set (narrows the type)."""
    assert series.id is not None
    return series.id


async def _seed_series(repo: SQLAlchemySeriesRepository, count: int) -> list[Series]:
    """Save ``count`` series with sequential titles."""
    series_list = [_create_series(title=f"Series {i}") for i in range(count)]
    for series in series_list:
        await repo.save(series)
    return series_list


@pytest.mark.integration
class TestSQLAlchemySeriesRepository:
    """Integration tests for series repository operations."""

    async def test_save_creates_new_series(self, db_session: AsyncSession) -> None:
        """Test that save persists a new series."""
        repo = SQLAlchemySeriesRepository(db_session)
        series = _create_series(title="Breaking Bad", start_year=2008)

        saved = await repo.save(series)

        assert saved.id == series.id
        assert saved.title.value == "Breaking Bad"
        assert saved.start_year.value == 2008

    async def test_save_creates_series_with_seasons(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Test that save persists series with seasons."""
        repo = SQLAlchemySeriesRepository(db_session)
        series = _create_series(
            title="The Office",
            season_count=2,
            episodes_per_season=0,
        )

        saved = await repo.save(series)

        assert saved.season_count == 2
        assert saved.seasons[0].season_number == SeasonNumber(1)
        assert saved.seasons[1].season_number == SeasonNumber(2)

    async def test_save_creates_series_with_episodes(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Test that save persists series with seasons and episodes."""
        repo = SQLAlchemySeriesRepository(db_session)
        series = _create_series(
            title="Friends",
            season_count=2,
            episodes_per_season=3,
        )

        saved = await repo.save(series)

        assert saved.total_episodes == 6
        assert saved.seasons[0].episode_count == 3
        assert saved.seasons[1].episode_count == 3

    async def test_save_updates_existing_series(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Test that save updates an existing series."""
        repo = SQLAlchemySeriesRepository(db_session)
        series = _create_series(title="Original Title")
        await repo.save(series)

        updated = Series(
            library_id=_LIBRARY_ID,
            id=series.id,
            title=Title("Updated Title"),
            start_year=series.start_year,
            end_year=Year(2023),
            seasons=[],
        )
        saved = await repo.save(updated)

        assert saved.title.value == "Updated Title"
        assert saved.end_year is not None
        assert saved.end_year.value == 2023

    async def test_find_by_id_returns_series_with_seasons(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Test that find_by_id returns series with all seasons and episodes."""
        repo = SQLAlchemySeriesRepository(db_session)
        series = _create_series(
            title="Game of Thrones",
            season_count=2,
            episodes_per_season=2,
        )
        await repo.save(series)

        found = await repo.find_by_id(series.id)  # type: ignore[arg-type]

        assert found is not None
        assert found.title.value == "Game of Thrones"
        assert found.season_count == 2
        assert found.total_episodes == 4

    async def test_find_by_id_returns_none_for_nonexistent(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Test that find_by_id returns None for non-existent series."""
        repo = SQLAlchemySeriesRepository(db_session)

        found = await repo.find_by_id(SeriesId.generate())

        assert found is None

    async def test_delete_removes_series_and_children(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Test that delete removes series with all seasons and episodes."""
        repo = SQLAlchemySeriesRepository(db_session)
        series = _create_series(season_count=2, episodes_per_season=3)
        await repo.save(series)

        deleted = await repo.delete(series.id)  # type: ignore[arg-type]

        assert deleted is True
        assert await repo.find_by_id(series.id) is None  # type: ignore[arg-type]

    async def test_delete_returns_false_for_nonexistent(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Test that delete returns False for non-existent series."""
        repo = SQLAlchemySeriesRepository(db_session)

        deleted = await repo.delete(SeriesId.generate())

        assert deleted is False

    async def test_list_all_returns_all_series(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Test that list_all returns all series ordered by title."""
        repo = SQLAlchemySeriesRepository(db_session)
        series1 = _create_series(title="Zorro")
        series2 = _create_series(title="Arrow")
        series3 = _create_series(title="Barry")

        await repo.save(series1)
        await repo.save(series2)
        await repo.save(series3)

        all_series = await repo.list_all()

        assert len(all_series) == 3
        assert all_series[0].title.value == "Arrow"
        assert all_series[1].title.value == "Barry"
        assert all_series[2].title.value == "Zorro"

    async def test_list_all_returns_empty_when_no_series(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Test that list_all returns empty sequence when no series exist."""
        repo = SQLAlchemySeriesRepository(db_session)

        all_series = await repo.list_all()

        assert len(all_series) == 0

    async def test_find_by_file_path_returns_series(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Test that find_by_file_path finds series by episode file path."""
        repo = SQLAlchemySeriesRepository(db_session)
        series_id = SeriesId.generate()
        episode = _create_episode(
            series_id,
            file_path="/media/series/show/s01e01.mkv",
        )
        season = Season(
            id=SeasonId.generate(),
            series_id=series_id,
            season_number=1,
            episodes=[episode],
        )
        series = Series(
            library_id=_LIBRARY_ID,
            id=series_id,
            title=Title("My Show"),
            start_year=Year(2020),
            seasons=[season],
        )
        await repo.save(series)

        found = await repo.find_by_file_path(
            FilePath("/media/series/show/s01e01.mkv"),
        )

        assert found is not None
        assert found.id == series_id

    async def test_find_by_file_path_returns_none_for_nonexistent(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Test that find_by_file_path returns None for unknown path."""
        repo = SQLAlchemySeriesRepository(db_session)

        found = await repo.find_by_file_path(FilePath("/nonexistent/path.mkv"))

        assert found is None

    async def test_save_series_with_all_optional_fields(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Test saving a series with all optional fields populated."""
        repo = SQLAlchemySeriesRepository(db_session)
        series = _create_series(
            title="Full Series",
            original_title=Title("Original Full Series"),
            end_year=Year(2023),
            synopsis="A complete test series.",
            poster_path=ImageUrl("/posters/full.jpg"),
            backdrop_path=ImageUrl("/backdrops/full.jpg"),
            genres=[Genre("Drama"), Genre("Comedy")],
            tmdb_id=TmdbId(98765),
            imdb_id=ImdbId("tt9876543"),
        )

        saved = await repo.save(series)

        assert saved.original_title is not None
        assert saved.original_title.value == "Original Full Series"
        assert saved.end_year is not None
        assert saved.end_year.value == 2023
        assert saved.synopsis == "A complete test series."
        assert len(saved.genres) == 2
        assert saved.tmdb_id == TmdbId(98765)
        assert saved.imdb_id == ImdbId("tt9876543")

    async def test_update_adds_new_season(self, db_session: AsyncSession) -> None:
        """Test that updating a series can add a new season."""
        repo = SQLAlchemySeriesRepository(db_session)
        series = _create_series(title="Growing Show", season_count=1)
        await repo.save(series)

        # Add a second season
        new_season = _create_season(series.id, season_number=2, episode_count=2)  # type: ignore[arg-type]
        updated_series = Series(
            library_id=_LIBRARY_ID,
            id=series.id,
            title=series.title,
            start_year=series.start_year,
            seasons=[*series.seasons, new_season],
        )
        saved = await repo.save(updated_series)

        assert saved.season_count == 2
        assert saved.seasons[1].season_number == SeasonNumber(2)

    async def test_update_removes_season(self, db_session: AsyncSession) -> None:
        """Test that updating a series can remove a season."""
        repo = SQLAlchemySeriesRepository(db_session)
        series = _create_series(title="Shrinking Show", season_count=2)
        await repo.save(series)

        # Remove the second season
        updated_series = Series(
            library_id=_LIBRARY_ID,
            id=series.id,
            title=series.title,
            start_year=series.start_year,
            seasons=[series.seasons[0]],
        )
        saved = await repo.save(updated_series)

        assert saved.season_count == 1

    async def test_is_ongoing_property(self, db_session: AsyncSession) -> None:
        """Test that is_ongoing property works correctly."""
        repo = SQLAlchemySeriesRepository(db_session)

        ongoing = _create_series(title="Ongoing", end_year=None)
        ended = _create_series(title="Ended", end_year=Year(2022))

        await repo.save(ongoing)
        await repo.save(ended)

        found_ongoing = await repo.find_by_id(ongoing.id)  # type: ignore[arg-type]
        found_ended = await repo.find_by_id(ended.id)  # type: ignore[arg-type]

        assert found_ongoing is not None
        assert found_ongoing.is_ongoing is True

        assert found_ended is not None
        assert found_ended.is_ongoing is False

    async def test_update_adds_episode_to_season(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Test that updating a series can add episodes to existing season."""
        repo = SQLAlchemySeriesRepository(db_session)
        series = _create_series(
            title="Growing Episodes",
            season_count=1,
            episodes_per_season=1,
        )
        saved = await repo.save(series)

        # Add a second episode to the first season
        new_episode = _create_episode(
            saved.id,  # type: ignore[arg-type]
            season_number=1,
            episode_number=2,
            title="Second Episode",
            file_path="/series/s01e02.mkv",
        )
        updated_season = Season(
            id=saved.seasons[0].id,
            series_id=saved.id,
            season_number=1,
            title=saved.seasons[0].title,
            episodes=[*saved.seasons[0].episodes, new_episode],
        )
        updated_series = Series(
            library_id=_LIBRARY_ID,
            id=saved.id,
            title=saved.title,
            start_year=saved.start_year,
            seasons=[updated_season],
        )

        result = await repo.save(updated_series)

        assert result.seasons[0].episode_count == 2

    async def test_update_removes_episode_from_season(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Test that updating a series can remove episodes from existing season."""
        repo = SQLAlchemySeriesRepository(db_session)
        series = _create_series(
            title="Shrinking Episodes",
            season_count=1,
            episodes_per_season=2,
        )
        saved = await repo.save(series)

        # Remove the second episode
        updated_season = Season(
            id=saved.seasons[0].id,
            series_id=saved.id,
            season_number=1,
            title=saved.seasons[0].title,
            episodes=[saved.seasons[0].episodes[0]],
        )
        updated_series = Series(
            library_id=_LIBRARY_ID,
            id=saved.id,
            title=saved.title,
            start_year=saved.start_year,
            seasons=[updated_season],
        )

        result = await repo.save(updated_series)

        assert result.seasons[0].episode_count == 1

    async def test_update_modifies_episode_data(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Test that updating a series can modify existing episode data."""
        repo = SQLAlchemySeriesRepository(db_session)
        series = _create_series(
            title="Modifying Episodes",
            season_count=1,
            episodes_per_season=1,
        )
        saved = await repo.save(series)

        # Modify the episode title
        original_episode = saved.seasons[0].episodes[0]
        updated_episode = Episode(
            id=original_episode.id,
            series_id=saved.id,
            season_number=1,
            episode_number=1,
            title=Title("Updated Episode Title"),
            duration=original_episode.duration,
            files=original_episode.files,
        )
        updated_season = Season(
            id=saved.seasons[0].id,
            series_id=saved.id,
            season_number=1,
            title=saved.seasons[0].title,
            episodes=[updated_episode],
        )
        updated_series = Series(
            library_id=_LIBRARY_ID,
            id=saved.id,
            title=saved.title,
            start_year=saved.start_year,
            seasons=[updated_season],
        )

        result = await repo.save(updated_series)

        assert result.seasons[0].episodes[0].title.value == "Updated Episode Title"


@pytest.mark.integration
class TestSQLAlchemySeriesRepositoryFindRandom:
    """Tests for find_random."""

    async def test_find_random_should_return_requested_limit(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemySeriesRepository(db_session)
        await _seed_series(repo, count=5)

        result = await repo.find_random(limit=3)

        assert len(result) == 3

    async def test_find_random_with_backdrop_should_filter(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemySeriesRepository(db_session)
        await repo.save(
            _create_series(
                title="With Backdrop",
                backdrop_path=ImageUrl("https://image.tmdb.org/backdrop.jpg"),
            ),
        )
        await repo.save(_create_series(title="No Backdrop"))

        result = await repo.find_random(limit=10, with_backdrop=True)

        assert len(result) == 1
        assert result[0].title.value == "With Backdrop"

    async def test_find_random_should_exclude_deleted(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemySeriesRepository(db_session)
        kept = _create_series(title="Kept")
        deleted = _create_series(title="Deleted")
        await repo.save(kept)
        await repo.save(deleted)
        await repo.delete(_id_of(deleted))

        result = await repo.find_random(limit=10)

        assert len(result) == 1
        assert result[0].title.value == "Kept"


@pytest.mark.integration
class TestSQLAlchemySeriesRepositoryFindByIds:
    """Tests for find_by_ids."""

    async def test_find_by_ids_should_return_empty_dict_for_empty_input(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemySeriesRepository(db_session)

        result = await repo.find_by_ids([])

        assert result == {}

    async def test_find_by_ids_should_return_mapping_by_external_id(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemySeriesRepository(db_session)
        seeded = await _seed_series(repo, count=2)
        ids = [_id_of(s) for s in seeded]

        result = await repo.find_by_ids(ids)

        assert len(result) == 2
        for series_id in ids:
            assert str(series_id) in result

    async def test_find_by_ids_should_skip_missing(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemySeriesRepository(db_session)
        series = _create_series(title="Exists")
        await repo.save(series)

        result = await repo.find_by_ids([_id_of(series), SeriesId.generate()])

        assert len(result) == 1
        assert str(series.id) in result

    async def test_find_by_ids_should_exclude_deleted(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemySeriesRepository(db_session)
        series = _create_series(title="Deleted")
        await repo.save(series)
        series_id = _id_of(series)
        await repo.delete(series_id)

        result = await repo.find_by_ids([series_id])

        assert result == {}


@pytest.mark.integration
class TestSQLAlchemySeriesRepositoryFindByTmdbIds:
    """Tests for ``find_by_tmdb_ids`` — used by ``GetRelatedSeries``."""

    async def test_returns_empty_dict_for_empty_input(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemySeriesRepository(db_session)
        assert await repo.find_by_tmdb_ids([]) == {}

    async def test_returns_mapping_by_tmdb_id(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemySeriesRepository(db_session)
        a = _create_series(title="A", tmdb_id=TmdbId(100))
        b = _create_series(title="B", tmdb_id=TmdbId(200))
        await repo.save(a)
        await repo.save(b)

        result = await repo.find_by_tmdb_ids([100, 200])

        assert set(result.keys()) == {100, 200}
        assert result[100].title.value == "A"
        assert result[200].title.value == "B"

    async def test_skips_ids_not_in_catalog(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemySeriesRepository(db_session)
        present = _create_series(title="Present", tmdb_id=TmdbId(42))
        await repo.save(present)

        result = await repo.find_by_tmdb_ids([42, 9999])

        assert set(result.keys()) == {42}

    async def test_excludes_soft_deleted(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemySeriesRepository(db_session)
        series = _create_series(title="Trashed", tmdb_id=TmdbId(7))
        await repo.save(series)
        await repo.delete(_id_of(series))

        assert await repo.find_by_tmdb_ids([7]) == {}

    async def test_skips_series_with_null_tmdb_id(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemySeriesRepository(db_session)
        no_tmdb = _create_series(title="Manual")
        await repo.save(no_tmdb)

        assert await repo.find_by_tmdb_ids([1, 2, 3]) == {}


@pytest.mark.integration
class TestSQLAlchemySeriesRepositoryFindByTitle:
    """Tests for find_by_title."""

    async def test_find_by_title_should_return_series(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemySeriesRepository(db_session)
        await repo.save(_create_series(title="Breaking Bad"))

        result = await repo.find_by_title(Title("Breaking Bad"))

        assert result is not None
        assert result.title.value == "Breaking Bad"

    async def test_find_by_title_should_be_case_insensitive(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemySeriesRepository(db_session)
        await repo.save(_create_series(title="Breaking Bad"))

        result = await repo.find_by_title(Title("breaking bad"))

        assert result is not None

    async def test_find_by_title_should_return_none_when_missing(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemySeriesRepository(db_session)

        result = await repo.find_by_title(Title("Nonexistent"))

        assert result is None


@pytest.mark.integration
class TestSQLAlchemySeriesRepositoryFindByEpisodeId:
    """Tests for find_by_episode_id."""

    async def test_find_by_episode_id_should_return_series(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemySeriesRepository(db_session)
        series = _create_series(
            title="With Episodes",
            season_count=1,
            episodes_per_season=2,
        )
        await repo.save(series)
        episode_id = series.seasons[0].episodes[0].id
        assert episode_id is not None

        result = await repo.find_by_episode_id(episode_id)

        assert result is not None
        assert result.id == series.id

    async def test_find_by_episode_id_should_return_none_when_missing(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemySeriesRepository(db_session)

        result = await repo.find_by_episode_id(EpisodeId.generate())

        assert result is None


@pytest.mark.integration
class TestSQLAlchemySeriesRepositorySaveRestore:
    """Tests for save restoring soft-deleted records."""

    async def test_save_should_restore_soft_deleted_series(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemySeriesRepository(db_session)
        series = _create_series(
            title="Restored",
            season_count=1,
            episodes_per_season=1,
        )
        await repo.save(series)
        series_id = _id_of(series)
        await repo.delete(series_id)

        # Re-save to restore
        restored = await repo.save(series)

        assert restored.id == series.id
        found = await repo.find_by_id(series_id)
        assert found is not None
        assert found.title.value == "Restored"


@pytest.mark.integration
class TestSQLAlchemySeriesRepositoryListPaginated:
    """Integration tests for the cursor-paginated listing."""

    async def test_should_return_first_page_when_cursor_is_none(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemySeriesRepository(db_session)
        await _seed_series(repo, count=5)

        page = await repo.list_paginated(cursor=None, limit=3)

        assert len(page.items) == 3
        assert page.pagination.has_more is True
        assert page.pagination.next_cursor is not None
        assert page.total_count is None

    async def test_should_walk_to_the_next_page_via_cursor(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemySeriesRepository(db_session)
        await _seed_series(repo, count=5)

        page1 = await repo.list_paginated(cursor=None, limit=2)
        page2 = await repo.list_paginated(cursor=page1.pagination.next_cursor, limit=2)
        page3 = await repo.list_paginated(cursor=page2.pagination.next_cursor, limit=2)

        page1_ids = {_id_of(s) for s in page1.items}
        page2_ids = {_id_of(s) for s in page2.items}
        page3_ids = {_id_of(s) for s in page3.items}

        assert page1_ids.isdisjoint(page2_ids)
        assert page2_ids.isdisjoint(page3_ids)
        assert len(page1.items) == 2
        assert len(page2.items) == 2
        assert len(page3.items) == 1
        assert page3.pagination.has_more is False
        assert page3.pagination.next_cursor is None

    async def test_should_return_has_more_false_when_exact_fit(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemySeriesRepository(db_session)
        await _seed_series(repo, count=3)

        page = await repo.list_paginated(cursor=None, limit=3)

        assert len(page.items) == 3
        assert page.pagination.has_more is False
        assert page.pagination.next_cursor is None

    async def test_should_return_empty_page_when_no_series(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemySeriesRepository(db_session)

        page = await repo.list_paginated(cursor=None, limit=20)

        assert page.items == []
        assert page.pagination.has_more is False
        assert page.pagination.next_cursor is None

    async def test_should_silently_fall_back_to_first_page_on_invalid_cursor(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemySeriesRepository(db_session)
        await _seed_series(repo, count=3)

        page = await repo.list_paginated(cursor="not-a-valid-cursor", limit=10)

        assert len(page.items) == 3

    async def test_should_order_by_id_desc(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemySeriesRepository(db_session)
        seeded = await _seed_series(repo, count=4)

        page = await repo.list_paginated(cursor=None, limit=4)

        returned_titles = [s.title.value for s in page.items]
        seeded_titles = [s.title.value for s in seeded]
        assert returned_titles == list(reversed(seeded_titles))

    async def test_should_exclude_soft_deleted_series(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemySeriesRepository(db_session)
        series_list = await _seed_series(repo, count=3)
        await repo.delete(_id_of(series_list[0]))

        page = await repo.list_paginated(cursor=None, limit=10)

        assert len(page.items) == 2
        returned_ids = {_id_of(s) for s in page.items}
        assert _id_of(series_list[0]) not in returned_ids

    async def test_should_populate_total_count_when_requested(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemySeriesRepository(db_session)
        await _seed_series(repo, count=7)

        page = await repo.list_paginated(cursor=None, limit=3, include_total=True)

        assert page.total_count == 7
        assert len(page.items) == 3
        assert page.pagination.has_more is True

    async def test_should_not_count_soft_deleted_in_total(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemySeriesRepository(db_session)
        series_list = await _seed_series(repo, count=5)
        await repo.delete(_id_of(series_list[0]))
        await repo.delete(_id_of(series_list[1]))

        page = await repo.list_paginated(cursor=None, limit=10, include_total=True)

        assert page.total_count == 3


@pytest.mark.integration
class TestSQLAlchemySeriesRepositoryListPaginatedAdminFilters:
    """Integration coverage for the admin Catalog ``q`` short-circuit
    on ``list_paginated``. The FTS5 hit path itself is exercised by
    the live ``/api/v1/series?q=...`` smoke flow because
    ``series_fts`` ships via Alembic, not
    ``Base.metadata.create_all``."""

    async def test_q_blank_should_short_circuit_the_fts_round_trip(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemySeriesRepository(db_session)
        await repo.save(_create_series(title="A"))
        await repo.save(_create_series(title="B"))

        page = await repo.list_paginated(cursor=None, limit=10, q="   ")

        assert {s.title.value for s in page.items} == {"A", "B"}


@pytest.mark.integration
class TestSQLAlchemySeriesRepositoryListRecentlyAdded:
    """Integration tests for the bounded "top N newest" projection."""

    async def test_should_return_series_in_id_desc_order(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemySeriesRepository(db_session)
        seeded = await _seed_series(repo, count=4)

        result = await repo.list_recently_added(limit=10)

        returned_titles = [s.title.value for s in result]
        assert returned_titles == list(reversed([s.title.value for s in seeded]))

    async def test_should_clamp_to_limit(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemySeriesRepository(db_session)
        await _seed_series(repo, count=5)

        result = await repo.list_recently_added(limit=3)

        assert len(result) == 3

    async def test_should_return_all_when_limit_exceeds_total(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemySeriesRepository(db_session)
        await _seed_series(repo, count=2)

        result = await repo.list_recently_added(limit=10)

        assert len(result) == 2

    async def test_should_exclude_soft_deleted(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemySeriesRepository(db_session)
        series_list = await _seed_series(repo, count=3)
        await repo.delete(_id_of(series_list[-1]))

        result = await repo.list_recently_added(limit=10)

        returned_ids = {_id_of(s) for s in result}
        assert _id_of(series_list[-1]) not in returned_ids
        assert len(result) == 2

    async def test_should_return_empty_when_no_series(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemySeriesRepository(db_session)

        result = await repo.list_recently_added(limit=10)

        assert list(result) == []


@pytest.mark.integration
class TestSQLAlchemySeriesRepositoryListGenreRows:
    """Integration tests for the lightweight genre projection."""

    async def test_should_return_one_row_per_series(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemySeriesRepository(db_session)
        await repo.save(_create_series(title="A", genres=[Genre("Drama")]))
        await repo.save(_create_series(title="B", genres=[Genre("Comedy")]))

        rows = await repo.list_genre_rows(lang="en")

        assert len(rows) == 2

    async def test_should_split_comma_separated_genres(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemySeriesRepository(db_session)
        series = _create_series(
            title="A",
            genres=[Genre("Drama"), Genre("Crime"), Genre("Thriller")],
        )
        await repo.save(series)

        rows = await repo.list_genre_rows(lang="en")

        assert rows[0].canonical_genres == ["Drama", "Crime", "Thriller"]

    async def test_should_skip_rows_with_no_genres(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemySeriesRepository(db_session)
        await repo.save(_create_series(title="A", genres=[Genre("Drama")]))
        await repo.save(_create_series(title="B"))

        rows = await repo.list_genre_rows(lang="en")

        assert len(rows) == 1

    async def test_should_exclude_soft_deleted(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemySeriesRepository(db_session)
        s1 = _create_series(title="A", genres=[Genre("Drama")])
        s2 = _create_series(title="B", genres=[Genre("Comedy")])
        await repo.save(s1)
        await repo.save(s2)
        await repo.delete(_id_of(s1))

        rows = await repo.list_genre_rows(lang="en")

        assert len(rows) == 1
        assert rows[0].canonical_genres == ["Comedy"]


@pytest.mark.integration
class TestSQLAlchemySeriesRepositoryListPaginatedByGenre:
    """Integration tests for the title-sorted, genre-filtered listing."""

    async def test_should_filter_to_series_with_the_given_genre(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemySeriesRepository(db_session)
        await repo.save(_create_series(title="Breaking Bad", genres=[Genre("Drama")]))
        await repo.save(_create_series(title="Friends", genres=[Genre("Comedy")]))

        page = await repo.list_paginated_by_genre(genre=Genre("Drama"), cursor=None, limit=10)

        assert len(page.items) == 1
        assert page.items[0].title.value == "Breaking Bad"

    async def test_should_not_match_substrings_or_partial_words(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemySeriesRepository(db_session)
        await repo.save(_create_series(title="A", genres=[Genre("Dramedy")]))
        await repo.save(_create_series(title="B", genres=[Genre("Drama Comedy")]))
        await repo.save(_create_series(title="C", genres=[Genre("Drama")]))

        page = await repo.list_paginated_by_genre(genre=Genre("Drama"), cursor=None, limit=10)

        assert len(page.items) == 1
        assert page.items[0].title.value == "C"

    async def test_should_sort_alphabetically_case_insensitive(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemySeriesRepository(db_session)
        for title in ["zebra", "Apple", "mango", "Banana"]:
            await repo.save(_create_series(title=title, genres=[Genre("Drama")]))

        page = await repo.list_paginated_by_genre(genre=Genre("Drama"), cursor=None, limit=10)

        titles = [s.title.value for s in page.items]
        assert titles == ["Apple", "Banana", "mango", "zebra"]

    async def test_should_walk_pages_via_cursor(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemySeriesRepository(db_session)
        for title in ["Alpha", "Beta", "Gamma", "Delta", "Epsilon"]:
            await repo.save(_create_series(title=title, genres=[Genre("Drama")]))

        page1 = await repo.list_paginated_by_genre(genre=Genre("Drama"), cursor=None, limit=2)
        page2 = await repo.list_paginated_by_genre(
            genre=Genre("Drama"),
            cursor=page1.pagination.next_cursor,
            limit=2,
        )
        page3 = await repo.list_paginated_by_genre(
            genre=Genre("Drama"),
            cursor=page2.pagination.next_cursor,
            limit=2,
        )

        all_titles = (
            [s.title.value for s in page1.items]
            + [s.title.value for s in page2.items]
            + [s.title.value for s in page3.items]
        )
        assert all_titles == ["Alpha", "Beta", "Delta", "Epsilon", "Gamma"]
        assert page3.pagination.has_more is False

    async def test_should_populate_per_item_cursors(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemySeriesRepository(db_session)
        for title in ["Alpha", "Beta", "Gamma"]:
            await repo.save(_create_series(title=title, genres=[Genre("Drama")]))

        page = await repo.list_paginated_by_genre(genre=Genre("Drama"), cursor=None, limit=10)

        assert page.item_cursors is not None
        assert len(page.item_cursors) == len(page.items) == 3

    async def test_should_exclude_soft_deleted(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemySeriesRepository(db_session)
        s1 = _create_series(title="A", genres=[Genre("Drama")])
        s2 = _create_series(title="B", genres=[Genre("Drama")])
        await repo.save(s1)
        await repo.save(s2)
        await repo.delete(_id_of(s1))

        page = await repo.list_paginated_by_genre(genre=Genre("Drama"), cursor=None, limit=10)

        assert len(page.items) == 1
        assert page.items[0].title.value == "B"


def _series_with_episode_paths(
    title: str,
    paths: list[str],
    start_year: int = 2020,
) -> Series:
    """Build a series whose single season has one episode per path."""
    sid = SeriesId.generate()
    episodes = [
        _create_episode(sid, season_number=1, episode_number=i + 1, file_path=p)
        for i, p in enumerate(paths)
    ]
    season = Season(
        id=SeasonId.generate(),
        series_id=sid,
        season_number=1,
        title=Title("Season 1"),
        episodes=episodes,
    )
    return Series(
        library_id=_LIBRARY_ID,
        id=sid,
        title=Title(title),
        start_year=Year(start_year),
        seasons=[season],
    )


@pytest.mark.integration
class TestSeriesCountUnderPaths:
    """Integration tests for ``SQLAlchemySeriesRepository.count_under_paths``."""

    async def test_returns_zero_for_empty_paths(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemySeriesRepository(db_session)
        await repo.save(_series_with_episode_paths("A", ["/media/tv/a/s01e01.mkv"]))

        assert await repo.count_under_paths([]) == 0

    async def test_counts_series_with_matching_episode(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemySeriesRepository(db_session)
        await repo.save(_series_with_episode_paths("A", ["/media/tv/a/s01e01.mkv"]))
        await repo.save(_series_with_episode_paths("B", ["/media/tv/b/s01e01.mkv"]))
        await repo.save(_series_with_episode_paths("Other", ["/elsewhere/x/s01e01.mkv"]))

        assert await repo.count_under_paths(["/media/tv"]) == 2

    async def test_counts_distinct_series_not_episodes(self, db_session: AsyncSession) -> None:
        """A series with N matching episodes still counts as one."""
        repo = SQLAlchemySeriesRepository(db_session)
        await repo.save(
            _series_with_episode_paths(
                "Multi",
                [
                    "/media/tv/multi/s01e01.mkv",
                    "/media/tv/multi/s01e02.mkv",
                    "/media/tv/multi/s01e03.mkv",
                ],
            )
        )

        assert await repo.count_under_paths(["/media/tv"]) == 1

    async def test_matches_windows_prefix(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemySeriesRepository(db_session)
        await repo.save(_series_with_episode_paths("W", [r"D:\homeflix\tv\show\s01e01.mkv"]))
        await repo.save(_series_with_episode_paths("Other", [r"E:\other\s01e01.mkv"]))

        assert await repo.count_under_paths([r"D:\homeflix"]) == 1

    async def test_excludes_soft_deleted_series(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemySeriesRepository(db_session)
        a = _series_with_episode_paths("A", ["/media/tv/a/s01e01.mkv"])
        b = _series_with_episode_paths("B", ["/media/tv/b/s01e01.mkv"])
        await repo.save(a)
        await repo.save(b)
        await repo.delete(_id_of(a))

        # The delete cascades to episodes, so A's episode is also
        # soft-deleted and shouldn't keep the series in the count.
        assert await repo.count_under_paths(["/media/tv"]) == 1

    async def test_normalizes_trailing_separator(self, db_session: AsyncSession) -> None:
        """A trailing ``/`` on the filter path must still match episode rows."""
        repo = SQLAlchemySeriesRepository(db_session)
        await repo.save(_series_with_episode_paths("A", ["/media/tv/a/s01e01.mkv"]))

        assert await repo.count_under_paths(["/media/tv/"]) == 1


def _series_with_intro(
    *,
    intro: IntroMarker | None = None,
    detection_state: IntroDetectionState = IntroDetectionState.NOT_STARTED,
    detection_attempted_at: datetime | None = None,
    detection_error: str | None = None,
    series_title: str = "Intro Series",
) -> Series:
    """Build a single-season, single-episode series with the given intro state.

    The episode file path is derived from the series id so callers can
    save multiple series in the same test without colliding on the
    ``episodes.file_path`` unique constraint.
    """
    sid = SeriesId.generate()
    episode = _create_episode(sid, file_path=f"/series/{sid}/s01e01.mkv")
    if intro is not None:
        episode = episode.with_intro_marker(intro)

    season = Season(
        id=SeasonId.generate(),
        series_id=sid,
        season_number=1,
        title=Title("Season 1"),
        episodes=[episode],
        intro_detection_state=detection_state,
        intro_detection_attempted_at=detection_attempted_at,
        intro_detection_error=detection_error,
    )
    return Series(
        library_id=_LIBRARY_ID,
        id=sid,
        title=Title(series_title),
        start_year=Year(2020),
        seasons=[season],
    )


@pytest.mark.integration
class TestSQLAlchemySeriesRepositoryCount:
    """Integration tests for the catalog-wide ``count`` method."""

    async def test_should_return_zero_for_empty_catalog(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemySeriesRepository(db_session)
        assert await repo.count() == 0

    async def test_should_count_every_non_deleted_series(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemySeriesRepository(db_session)
        await _seed_series(repo, 3)

        assert await repo.count() == 3

    async def test_should_exclude_soft_deleted(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemySeriesRepository(db_session)
        keep, doomed = await _seed_series(repo, 2)
        await repo.delete(_id_of(doomed))

        assert await repo.count() == 1
        # Sanity-check the surviving row is the one we kept.
        assert (await repo.find_by_id(_id_of(keep))) is not None


@pytest.mark.integration
class TestSeriesRepositoryIntroPersistence:
    """Tests covering IntroMarker and Season detection-state persistence."""

    async def test_episode_round_trip_without_intro_keeps_columns_null(
        self,
        db_session: AsyncSession,
    ) -> None:
        repo = SQLAlchemySeriesRepository(db_session)
        series = _create_series(season_count=1, episodes_per_season=1)
        await repo.save(series)

        found = await repo.find_by_id(series.id)  # type: ignore[arg-type]

        assert found is not None
        assert found.seasons[0].episodes[0].intro is None

    async def test_episode_round_trip_with_manual_intro(
        self,
        db_session: AsyncSession,
    ) -> None:
        repo = SQLAlchemySeriesRepository(db_session)
        marker = IntroMarker(
            start_seconds=10,
            end_seconds=72,
            source=IntroMarkerSource.MANUAL,
            detected_at=datetime(2026, 4, 29, 12, 0, tzinfo=UTC),
        )
        series = _series_with_intro(intro=marker)
        await repo.save(series)

        found = await repo.find_by_id(series.id)  # type: ignore[arg-type]

        assert found is not None
        episode = found.seasons[0].episodes[0]
        assert episode.intro is not None
        assert episode.intro.start_seconds == 10
        assert episode.intro.end_seconds == 72
        assert episode.intro.source == IntroMarkerSource.MANUAL
        assert episode.intro.confidence is None

    async def test_episode_round_trip_with_auto_detected_intro(
        self,
        db_session: AsyncSession,
    ) -> None:
        repo = SQLAlchemySeriesRepository(db_session)
        marker = IntroMarker(
            start_seconds=12,
            end_seconds=98,
            source=IntroMarkerSource.AUTO_DETECTED,
            confidence=0.91,
        )
        series = _series_with_intro(intro=marker)
        await repo.save(series)

        found = await repo.find_by_id(series.id)  # type: ignore[arg-type]

        assert found is not None
        episode = found.seasons[0].episodes[0]
        assert episode.intro is not None
        assert episode.intro.source == IntroMarkerSource.AUTO_DETECTED
        assert episode.intro.confidence == pytest.approx(0.91)

    async def test_save_clears_intro_when_entity_intro_is_none(
        self,
        db_session: AsyncSession,
    ) -> None:
        repo = SQLAlchemySeriesRepository(db_session)
        marker = IntroMarker(
            start_seconds=0,
            end_seconds=60,
            source=IntroMarkerSource.MANUAL,
        )
        series = _series_with_intro(intro=marker)
        await repo.save(series)

        # Round-trip, then clear the intro and persist again.
        found = await repo.find_by_id(series.id)  # type: ignore[arg-type]
        assert found is not None
        cleared_episode = found.seasons[0].episodes[0].with_intro_cleared()
        cleared_season = found.seasons[0].with_updates(episodes=[cleared_episode])
        cleared_series = found.with_updates(seasons=[cleared_season])
        await repo.save(cleared_series)

        roundtrip = await repo.find_by_id(series.id)  # type: ignore[arg-type]
        assert roundtrip is not None
        assert roundtrip.seasons[0].episodes[0].intro is None

    async def test_season_detection_state_round_trip(
        self,
        db_session: AsyncSession,
    ) -> None:
        repo = SQLAlchemySeriesRepository(db_session)
        attempted_at = datetime(2026, 4, 29, 18, 0, tzinfo=UTC)
        series = _series_with_intro(
            detection_state=IntroDetectionState.FAILED,
            detection_attempted_at=attempted_at,
            detection_error="ffmpeg returned non-zero",
        )
        await repo.save(series)

        found = await repo.find_by_id(series.id)  # type: ignore[arg-type]

        assert found is not None
        season = found.seasons[0]
        assert season.intro_detection_state == IntroDetectionState.FAILED
        assert season.intro_detection_error == "ffmpeg returned non-zero"
        assert season.intro_detection_attempted_at is not None


@pytest.mark.integration
class TestFindSeasonsPendingIntroDetection:
    """Tests for find_seasons_pending_intro_detection."""

    async def test_returns_only_not_started_and_insufficient_seasons(
        self,
        db_session: AsyncSession,
    ) -> None:
        repo = SQLAlchemySeriesRepository(db_session)

        await repo.save(
            _series_with_intro(
                detection_state=IntroDetectionState.NOT_STARTED,
                series_title="A — pending",
            )
        )
        await repo.save(
            _series_with_intro(
                detection_state=IntroDetectionState.INSUFFICIENT_EPISODES,
                series_title="B — retry",
            )
        )
        await repo.save(
            _series_with_intro(
                detection_state=IntroDetectionState.COMPLETED,
                series_title="C — done",
            )
        )
        await repo.save(
            _series_with_intro(
                detection_state=IntroDetectionState.DISABLED,
                series_title="D — disabled",
            )
        )
        await repo.save(
            _series_with_intro(
                detection_state=IntroDetectionState.FAILED,
                series_title="E — failed",
                detection_error="boom",
            )
        )

        pending = await repo.find_seasons_pending_intro_detection(limit=10)

        states = sorted(s.intro_detection_state.value for s in pending)
        assert states == ["INSUFFICIENT_EPISODES", "NOT_STARTED"]

    async def test_eager_loads_episodes_and_files(
        self,
        db_session: AsyncSession,
    ) -> None:
        repo = SQLAlchemySeriesRepository(db_session)
        await repo.save(_series_with_intro(detection_state=IntroDetectionState.NOT_STARTED))

        pending = await repo.find_seasons_pending_intro_detection(limit=10)

        assert len(pending) == 1
        season = pending[0]
        assert len(season.episodes) == 1
        assert season.episodes[0].primary_file is not None

    async def test_respects_limit(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemySeriesRepository(db_session)
        for i in range(3):
            await repo.save(
                _series_with_intro(
                    detection_state=IntroDetectionState.NOT_STARTED,
                    series_title=f"Series {i}",
                )
            )

        pending = await repo.find_seasons_pending_intro_detection(limit=2)

        assert len(pending) == 2


@pytest.mark.integration
class TestUpdateSeasonIntroDetection:
    """Tests for update_season_intro_detection direct UPDATE."""

    async def test_updates_state_and_error(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemySeriesRepository(db_session)
        series = _series_with_intro(detection_state=IntroDetectionState.NOT_STARTED)
        await repo.save(series)
        season_id = series.seasons[0].id
        assert season_id is not None

        attempted_at = datetime(2026, 4, 29, 19, 0, tzinfo=UTC)
        updated = await repo.update_season_intro_detection(
            season_id,
            IntroDetectionState.FAILED,
            attempted_at=attempted_at,
            error="ffmpeg crashed",
        )
        await db_session.commit()

        assert updated is True
        found = await repo.find_by_id(series.id)  # type: ignore[arg-type]
        assert found is not None
        season = found.seasons[0]
        assert season.intro_detection_state == IntroDetectionState.FAILED
        assert season.intro_detection_error == "ffmpeg crashed"

    async def test_returns_false_for_unknown_season(
        self,
        db_session: AsyncSession,
    ) -> None:
        repo = SQLAlchemySeriesRepository(db_session)

        updated = await repo.update_season_intro_detection(
            SeasonId.generate(),
            IntroDetectionState.COMPLETED,
        )

        assert updated is False

    async def test_leaves_attempted_at_untouched_when_none(
        self,
        db_session: AsyncSession,
    ) -> None:
        repo = SQLAlchemySeriesRepository(db_session)
        original_attempted = datetime(2026, 4, 1, 12, 0, tzinfo=UTC)
        series = _series_with_intro(
            detection_state=IntroDetectionState.COMPLETED,
            detection_attempted_at=original_attempted,
        )
        await repo.save(series)
        season_id = series.seasons[0].id
        assert season_id is not None

        # Transient transition without an attempted_at — must keep the
        # previous run's timestamp visible for observability.
        await repo.update_season_intro_detection(
            season_id,
            IntroDetectionState.IN_PROGRESS,
        )
        await db_session.commit()

        found = await repo.find_by_id(series.id)  # type: ignore[arg-type]
        assert found is not None
        assert found.seasons[0].intro_detection_attempted_at is not None


@pytest.mark.integration
class TestUpdateEpisodeIntro:
    """Tests for update_episode_intro direct UPDATE."""

    async def test_sets_marker_on_episode_with_no_intro(
        self,
        db_session: AsyncSession,
    ) -> None:
        repo = SQLAlchemySeriesRepository(db_session)
        series = _series_with_intro()
        await repo.save(series)
        episode_id = series.seasons[0].episodes[0].id
        assert episode_id is not None
        marker = IntroMarker(
            start_seconds=5,
            end_seconds=80,
            source=IntroMarkerSource.AUTO_DETECTED,
            confidence=0.83,
        )

        updated = await repo.update_episode_intro(episode_id, marker)
        await db_session.commit()

        assert updated is True
        found = await repo.find_by_id(series.id)  # type: ignore[arg-type]
        assert found is not None
        episode = found.seasons[0].episodes[0]
        assert episode.intro is not None
        assert episode.intro.start_seconds == 5
        assert episode.intro.source == IntroMarkerSource.AUTO_DETECTED

    async def test_clearing_marker_nulls_all_columns(
        self,
        db_session: AsyncSession,
    ) -> None:
        repo = SQLAlchemySeriesRepository(db_session)
        marker = IntroMarker(
            start_seconds=0,
            end_seconds=60,
            source=IntroMarkerSource.MANUAL,
        )
        series = _series_with_intro(intro=marker)
        await repo.save(series)
        episode_id = series.seasons[0].episodes[0].id
        assert episode_id is not None

        updated = await repo.update_episode_intro(episode_id, None)
        await db_session.commit()

        assert updated is True
        found = await repo.find_by_id(series.id)  # type: ignore[arg-type]
        assert found is not None
        assert found.seasons[0].episodes[0].intro is None

    async def test_returns_false_for_unknown_episode(
        self,
        db_session: AsyncSession,
    ) -> None:
        repo = SQLAlchemySeriesRepository(db_session)

        updated = await repo.update_episode_intro(EpisodeId.generate(), None)

        assert updated is False


@pytest.mark.integration
class TestSQLAlchemySeriesRepositoryLibraryIsolation:
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
        repo = SQLAlchemySeriesRepository(db_session)

        # Library A: two series
        await repo.save(_create_series(title="A1"))
        await repo.save(_create_series(title="A2"))

        # Library B (different library_id): one series
        series_b = Series(
            library_id=_LIBRARY_ID_OTHER,
            id=SeriesId.generate(),
            title=Title("B1"),
            start_year=Year(2024),
        )
        await repo.save(series_b)

        # Direct queries by library_id never leak across.
        rows_a = (
            (
                await db_session.execute(
                    select(SeriesModel).where(SeriesModel.library_id == _LIBRARY_ID)
                )
            )
            .scalars()
            .all()
        )
        rows_b = (
            (
                await db_session.execute(
                    select(SeriesModel).where(SeriesModel.library_id == _LIBRARY_ID_OTHER)
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
        repo = SQLAlchemySeriesRepository(db_session)
        series = _create_series(title="Scoped")

        await repo.save(series)
        assert series.id is not None
        found = await repo.find_by_id(series.id)

        assert found is not None
        assert found.library_id == _LIBRARY_ID


def _series_in_library(*, library_id: str, title: str) -> Series:
    """Build a Series with an explicit ``library_id`` for ACL tests."""
    return Series(
        library_id=library_id,
        id=SeriesId.generate(),
        title=Title(title),
        start_year=Year(2024),
    )


@pytest.mark.integration
class TestAllowedLibraryIdsFilter:
    """``allowed_library_ids`` kwarg restricts reads to a set of libraries.

    Mirror of the movies-side coverage: pin ``list_paginated`` and
    ``find_by_id`` at the repo boundary so the use cases can rely on
    the kwarg's semantics without re-asserting in every unit test.
    """

    async def test_list_paginated_includes_only_allowed_libraries(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemySeriesRepository(db_session)
        await repo.save(_series_in_library(library_id=_LIBRARY_ID, title="Visible"))
        await repo.save(_series_in_library(library_id=_LIBRARY_ID_OTHER, title="Hidden"))

        page = await repo.list_paginated(
            cursor=None,
            limit=10,
            allowed_library_ids=[_LIBRARY_ID],
        )

        titles = {s.title.value for s in page.items}
        assert titles == {"Visible"}
        assert "Hidden" not in titles

    async def test_list_paginated_excludes_libraries_outside_allowed_set(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemySeriesRepository(db_session)
        await repo.save(_series_in_library(library_id=_LIBRARY_ID, title="In A"))
        await repo.save(_series_in_library(library_id=_LIBRARY_ID_OTHER, title="In B"))

        # Allowed = library B only.
        page = await repo.list_paginated(
            cursor=None,
            limit=10,
            allowed_library_ids=[_LIBRARY_ID_OTHER],
        )

        titles = {s.title.value for s in page.items}
        assert titles == {"In B"}

    async def test_find_by_id_returns_none_for_row_outside_acl(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemySeriesRepository(db_session)
        series = _series_in_library(library_id=_LIBRARY_ID_OTHER, title="Forbidden")
        await repo.save(series)
        assert series.id is not None

        # Caller is restricted to library A — must NOT see the row.
        found = await repo.find_by_id(series.id, allowed_library_ids=[_LIBRARY_ID])

        assert found is None

    async def test_find_by_id_returns_row_when_inside_acl(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemySeriesRepository(db_session)
        series = _series_in_library(library_id=_LIBRARY_ID, title="Allowed")
        await repo.save(series)
        assert series.id is not None

        found = await repo.find_by_id(series.id, allowed_library_ids=[_LIBRARY_ID])

        assert found is not None
        assert found.title.value == "Allowed"
