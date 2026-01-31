"""Tests for Season entity."""

from datetime import date

import pytest

from src.domain.shared.models import DomainValidationError


class TestSeasonCreation:
    """Tests for Season instantiation."""

    def test_should_create_with_required_fields(self):
        from src.domain.media.entities import Season
        from src.domain.media.value_objects import SeasonId, SeriesId

        series_id = SeriesId.generate()
        season = Season(
            series_id=series_id,
            season_number=1,
        )

        assert season.id is None
        assert season.series_id == series_id
        assert season.season_number == 1
        assert season.episodes == []

    def test_should_create_with_explicit_id(self):
        from src.domain.media.entities import Season
        from src.domain.media.value_objects import SeasonId, SeriesId

        season_id = SeasonId.generate()
        season = Season(
            id=season_id,
            series_id=SeriesId.generate(),
            season_number=1,
        )

        assert season.id == season_id

    def test_should_accept_string_id_and_convert(self):
        from src.domain.media.entities import Season
        from src.domain.media.value_objects import SeasonId, SeriesId

        season = Season(
            id="ssn_abc123abc123",
            series_id=SeriesId.generate(),
            season_number=1,
        )

        assert isinstance(season.id, SeasonId)
        assert season.id.value == "ssn_abc123abc123"

    def test_should_allow_season_number_zero_for_specials(self):
        from src.domain.media.entities import Season
        from src.domain.media.value_objects import SeriesId

        season = Season(
            series_id=SeriesId.generate(),
            season_number=0,
        )

        assert season.season_number == 0

    def test_should_raise_error_for_negative_season_number(self):
        from src.domain.media.entities import Season
        from src.domain.media.value_objects import SeriesId

        with pytest.raises(DomainValidationError):
            Season(
                series_id=SeriesId.generate(),
                season_number=-1,
            )


class TestSeasonOptionalFields:
    """Tests for Season optional fields."""

    def test_should_create_with_title(self):
        from src.domain.media.entities import Season
        from src.domain.media.value_objects import SeriesId, Title

        season = Season(
            series_id=SeriesId.generate(),
            season_number=1,
            title=Title("Season One"),
        )

        assert season.title.value == "Season One"

    def test_should_create_with_synopsis(self):
        from src.domain.media.entities import Season
        from src.domain.media.value_objects import SeriesId

        season = Season(
            series_id=SeriesId.generate(),
            season_number=1,
            synopsis="The first season of the show.",
        )

        assert season.synopsis == "The first season of the show."

    def test_should_create_with_poster_path(self):
        from src.domain.media.entities import Season
        from src.domain.media.value_objects import FilePath, SeriesId

        season = Season(
            series_id=SeriesId.generate(),
            season_number=1,
            poster_path=FilePath("/posters/show_s01.jpg"),
        )

        assert season.poster_path is not None

    def test_should_create_with_air_date(self):
        from src.domain.media.entities import Season
        from src.domain.media.value_objects import SeriesId

        air_date = date(2024, 1, 15)
        season = Season(
            series_id=SeriesId.generate(),
            season_number=1,
            air_date=air_date,
        )

        assert season.air_date == air_date


class TestSeasonEpisodeManagement:
    """Tests for Season episode management."""

    def test_episode_count_should_return_zero_when_empty(self):
        from src.domain.media.entities import Season
        from src.domain.media.value_objects import SeriesId

        season = Season(
            series_id=SeriesId.generate(),
            season_number=1,
        )

        assert season.episode_count == 0

    def test_should_add_episode(self):
        from src.domain.media.entities import Episode, Season
        from src.domain.media.value_objects import (
            Duration,
            EpisodeId,
            FilePath,
            Resolution,
            SeriesId,
            Title,
        )

        series_id = SeriesId.generate()
        season = Season(
            series_id=series_id,
            season_number=1,
        )

        episode = Episode(
            id=EpisodeId.generate(),
            series_id=series_id,
            season_number=1,
            episode_number=1,
            title=Title("Pilot"),
            duration=Duration(2700),
            file_path=FilePath("/series/show/s01e01.mkv"),
            file_size=1_000_000_000,
            resolution=Resolution("1080p"),
        )

        season.add_episode(episode)

        assert season.episode_count == 1
        assert season.episodes[0] == episode

    def test_should_raise_error_when_adding_episode_with_wrong_series_id(self):
        from src.domain.media.entities import Episode, Season
        from src.domain.media.value_objects import (
            Duration,
            FilePath,
            Resolution,
            SeriesId,
            Title,
        )

        season = Season(
            series_id=SeriesId.generate(),
            season_number=1,
        )

        episode = Episode(
            series_id=SeriesId.generate(),  # Different series
            season_number=1,
            episode_number=1,
            title=Title("Pilot"),
            duration=Duration(2700),
            file_path=FilePath("/series/show/s01e01.mkv"),
            file_size=1_000_000_000,
            resolution=Resolution("1080p"),
        )

        with pytest.raises(ValueError, match="series_id"):
            season.add_episode(episode)

    def test_should_raise_error_when_adding_episode_with_wrong_season_number(self):
        from src.domain.media.entities import Episode, Season
        from src.domain.media.value_objects import (
            Duration,
            FilePath,
            Resolution,
            SeriesId,
            Title,
        )

        series_id = SeriesId.generate()
        season = Season(
            series_id=series_id,
            season_number=1,
        )

        episode = Episode(
            series_id=series_id,
            season_number=2,  # Different season
            episode_number=1,
            title=Title("Pilot"),
            duration=Duration(2700),
            file_path=FilePath("/series/show/s02e01.mkv"),
            file_size=1_000_000_000,
            resolution=Resolution("1080p"),
        )

        with pytest.raises(ValueError, match="season_number"):
            season.add_episode(episode)

    def test_should_get_episode_by_number(self):
        from src.domain.media.entities import Episode, Season
        from src.domain.media.value_objects import (
            Duration,
            EpisodeId,
            FilePath,
            Resolution,
            SeriesId,
            Title,
        )

        series_id = SeriesId.generate()
        season = Season(
            series_id=series_id,
            season_number=1,
        )

        episode = Episode(
            id=EpisodeId.generate(),
            series_id=series_id,
            season_number=1,
            episode_number=5,
            title=Title("Episode 5"),
            duration=Duration(2700),
            file_path=FilePath("/series/show/s01e05.mkv"),
            file_size=1_000_000_000,
            resolution=Resolution("1080p"),
        )

        season.add_episode(episode)

        found = season.get_episode(5)
        assert found == episode

    def test_should_return_none_when_episode_not_found(self):
        from src.domain.media.entities import Season
        from src.domain.media.value_objects import SeriesId

        season = Season(
            series_id=SeriesId.generate(),
            season_number=1,
        )

        found = season.get_episode(99)
        assert found is None


class TestSeasonEquality:
    """Tests for Season equality based on ID."""

    def test_should_be_equal_when_same_id(self):
        from src.domain.media.entities import Season
        from src.domain.media.value_objects import SeasonId, SeriesId

        season_id = SeasonId.generate()
        series_id = SeriesId.generate()

        season1 = Season(id=season_id, series_id=series_id, season_number=1)
        season2 = Season(id=season_id, series_id=series_id, season_number=1)

        assert season1 == season2

    def test_should_not_be_equal_when_different_id(self):
        from src.domain.media.entities import Season
        from src.domain.media.value_objects import SeasonId, SeriesId

        series_id = SeriesId.generate()

        season1 = Season(id=SeasonId.generate(), series_id=series_id, season_number=1)
        season2 = Season(id=SeasonId.generate(), series_id=series_id, season_number=1)

        assert season1 != season2
