"""Integration tests for SQLAlchemySeriesRepository."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.media.domain.entities import Episode, Season, Series
from src.modules.media.domain.value_objects import (
    Duration,
    EpisodeId,
    FilePath,
    Genre,
    ImageUrl,
    ImdbId,
    MediaFile,
    Resolution,
    SeasonId,
    SeriesId,
    Title,
    TmdbId,
    Year,
)
from src.modules.media.infrastructure.persistence.repositories import SQLAlchemySeriesRepository


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
        id=sid,
        title=Title(title),
        start_year=Year(start_year),
        seasons=seasons,
        **kwargs,
    )


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
        assert saved.seasons[0].season_number == 1
        assert saved.seasons[1].season_number == 2

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
            id=series.id,
            title=series.title,
            start_year=series.start_year,
            seasons=[*series.seasons, new_season],
        )
        saved = await repo.save(updated_series)

        assert saved.season_count == 2
        assert saved.seasons[1].season_number == 2

    async def test_update_removes_season(self, db_session: AsyncSession) -> None:
        """Test that updating a series can remove a season."""
        repo = SQLAlchemySeriesRepository(db_session)
        series = _create_series(title="Shrinking Show", season_count=2)
        await repo.save(series)

        # Remove the second season
        updated_series = Series(
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
        for i in range(5):
            await repo.save(_create_series(title=f"Series {i}"))

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
        await repo.delete(deleted.id)  # type: ignore[arg-type]

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
        series_a = _create_series(title="A")
        series_b = _create_series(title="B")
        await repo.save(series_a)
        await repo.save(series_b)

        result = await repo.find_by_ids([series_a.id, series_b.id])  # type: ignore[list-item]

        assert len(result) == 2
        assert str(series_a.id) in result
        assert str(series_b.id) in result

    async def test_find_by_ids_should_skip_missing(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemySeriesRepository(db_session)
        series = _create_series(title="Exists")
        await repo.save(series)
        missing = SeriesId.generate()

        result = await repo.find_by_ids([series.id, missing])  # type: ignore[list-item]

        assert len(result) == 1
        assert str(series.id) in result

    async def test_find_by_ids_should_exclude_deleted(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemySeriesRepository(db_session)
        series = _create_series(title="Deleted")
        await repo.save(series)
        await repo.delete(series.id)  # type: ignore[arg-type]

        result = await repo.find_by_ids([series.id])  # type: ignore[list-item]

        assert result == {}


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
        await repo.delete(series.id)  # type: ignore[arg-type]

        # Re-save to restore
        restored = await repo.save(series)

        assert restored.id == series.id
        found = await repo.find_by_id(series.id)  # type: ignore[arg-type]
        assert found is not None
        assert found.title.value == "Restored"
