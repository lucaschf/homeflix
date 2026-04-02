"""Unit tests for SeriesMapper, SeasonMapper, and EpisodeMapper."""

import pytest

from src.domain.media.entities import Episode, Season, Series
from src.domain.media.value_objects import (
    Duration,
    EpisodeId,
    FilePath,
    MediaFile,
    Resolution,
    SeasonId,
    SeriesId,
    Title,
    Year,
)
from src.infrastructure.persistence.mappers import EpisodeMapper, SeasonMapper, SeriesMapper


def _create_episode(
    episode_id: EpisodeId | None = None,
    series_id: SeriesId | None = None,
) -> Episode:
    """Create an Episode entity for testing."""
    return Episode(
        id=episode_id,
        series_id=series_id or SeriesId.generate(),
        season_number=1,
        episode_number=1,
        title=Title("Test Episode"),
        duration=Duration(2700),
        files=[
            MediaFile(
                file_path=FilePath("/series/s01e01.mkv"),
                file_size=500_000_000,
                resolution=Resolution("1080p"),
                is_primary=True,
            )
        ],
    )


def _create_season(
    season_id: SeasonId | None = None,
    series_id: SeriesId | None = None,
) -> Season:
    """Create a Season entity for testing."""
    return Season(
        id=season_id,
        series_id=series_id or SeriesId.generate(),
        season_number=1,
        title=Title("Season 1"),
    )


def _create_series(series_id: SeriesId | None = None) -> Series:
    """Create a Series entity for testing."""
    return Series(
        id=series_id,
        title=Title("Test Series"),
        start_year=Year(2020),
    )


@pytest.mark.unit
class TestEpisodeMapper:
    """Unit tests for EpisodeMapper."""

    def test_to_model_raises_when_id_is_none(self) -> None:
        """Test that to_model raises ValueError when entity has no ID."""
        episode = _create_episode(episode_id=None)

        with pytest.raises(ValueError, match="Cannot map entity without ID"):
            EpisodeMapper.to_model(episode, season_id=1)

    def test_to_model_converts_entity_correctly(self) -> None:
        """Test that to_model converts all fields correctly."""
        episode_id = EpisodeId.generate()
        series_id = SeriesId.generate()
        episode = _create_episode(episode_id=episode_id, series_id=series_id)

        model = EpisodeMapper.to_model(episode, season_id=42)

        assert model.external_id == str(episode_id)
        assert model.season_id == 42
        assert model.series_external_id == str(series_id)
        assert model.title == "Test Episode"


@pytest.mark.unit
class TestSeasonMapper:
    """Unit tests for SeasonMapper."""

    def test_to_model_raises_when_id_is_none(self) -> None:
        """Test that to_model raises ValueError when entity has no ID."""
        season = _create_season(season_id=None)

        with pytest.raises(ValueError, match="Cannot map entity without ID"):
            SeasonMapper.to_model(season, series_db_id=1)

    def test_to_model_converts_entity_correctly(self) -> None:
        """Test that to_model converts all fields correctly."""
        season_id = SeasonId.generate()
        series_id = SeriesId.generate()
        season = _create_season(season_id=season_id, series_id=series_id)

        model = SeasonMapper.to_model(season, series_db_id=42)

        assert model.external_id == str(season_id)
        assert model.series_id == 42
        assert model.series_external_id == str(series_id)


@pytest.mark.unit
class TestSeriesMapper:
    """Unit tests for SeriesMapper."""

    def test_to_model_raises_when_id_is_none(self) -> None:
        """Test that to_model raises ValueError when entity has no ID."""
        series = _create_series(series_id=None)

        with pytest.raises(ValueError, match="Cannot map entity without ID"):
            SeriesMapper.to_model(series)

    def test_to_model_converts_entity_correctly(self) -> None:
        """Test that to_model converts all fields correctly."""
        series_id = SeriesId.generate()
        series = _create_series(series_id=series_id)

        model = SeriesMapper.to_model(series)

        assert model.external_id == str(series_id)
        assert model.title == "Test Series"
        assert model.start_year == 2020
