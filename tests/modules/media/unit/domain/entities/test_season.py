"""Tests for Season entity."""

from datetime import date

import pytest

from src.building_blocks.domain.errors import (
    BusinessRuleViolationException,
    DomainValidationException,
)
from src.modules.media.domain.entities import Episode
from src.modules.media.domain.value_objects import (
    Duration,
    EpisodeId,
    FilePath,
    MediaFile,
    Resolution,
    SeriesId,
    Title,
)


def _make_episode(
    series_id: SeriesId,
    season_number: int = 1,
    episode_number: int = 1,
    episode_id: EpisodeId | None = None,
) -> Episode:
    """Create an Episode for testing."""
    return Episode(
        id=episode_id or EpisodeId.generate(),
        series_id=series_id,
        season_number=season_number,
        episode_number=episode_number,
        title=Title(f"Episode {episode_number}"),
        duration=Duration(2700),
        files=[
            MediaFile(
                file_path=FilePath(f"/series/show/s{season_number:02d}e{episode_number:02d}.mkv"),
                file_size=1_000_000_000,
                resolution=Resolution("1080p"),
                is_primary=True,
            )
        ],
    )


class TestSeasonCreation:
    """Tests for Season instantiation."""

    def test_should_create_with_required_fields(self):
        from src.modules.media.domain.entities import Season
        from src.modules.media.domain.value_objects import SeriesId

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
        from src.modules.media.domain.entities import Season
        from src.modules.media.domain.value_objects import SeasonId, SeriesId

        season_id = SeasonId.generate()
        season = Season(
            id=season_id,
            series_id=SeriesId.generate(),
            season_number=1,
        )

        assert season.id == season_id

    def test_should_accept_string_id_and_convert(self):
        from src.modules.media.domain.entities import Season
        from src.modules.media.domain.value_objects import SeasonId, SeriesId

        season = Season(
            id="ssn_abc123abc123",
            series_id=SeriesId.generate(),
            season_number=1,
        )

        assert isinstance(season.id, SeasonId)
        assert season.id.value == "ssn_abc123abc123"

    def test_should_allow_season_number_zero_for_specials(self):
        from src.modules.media.domain.entities import Season
        from src.modules.media.domain.value_objects import SeriesId

        season = Season(
            series_id=SeriesId.generate(),
            season_number=0,
        )

        assert season.season_number == 0

    def test_should_raise_error_for_negative_season_number(self):
        from src.modules.media.domain.entities import Season
        from src.modules.media.domain.value_objects import SeriesId

        with pytest.raises(DomainValidationException):
            Season(
                series_id=SeriesId.generate(),
                season_number=-1,
            )


class TestSeasonOptionalFields:
    """Tests for Season optional fields."""

    def test_should_create_with_title(self):
        from src.modules.media.domain.entities import Season
        from src.modules.media.domain.value_objects import SeriesId, Title

        season = Season(
            series_id=SeriesId.generate(),
            season_number=1,
            title=Title("Season One"),
        )

        assert season.title is not None
        assert season.title.value == "Season One"

    def test_should_create_with_synopsis(self):
        from src.modules.media.domain.entities import Season
        from src.modules.media.domain.value_objects import SeriesId

        season = Season(
            series_id=SeriesId.generate(),
            season_number=1,
            synopsis="The first season of the show.",
        )

        assert season.synopsis == "The first season of the show."

    def test_should_create_with_poster_path(self):
        from src.modules.media.domain.entities import Season
        from src.modules.media.domain.value_objects import ImageUrl, SeriesId

        season = Season(
            series_id=SeriesId.generate(),
            season_number=1,
            poster_path=ImageUrl("/posters/show_s01.jpg"),
        )

        assert season.poster_path is not None

    def test_should_create_with_air_date(self):
        from src.modules.media.domain.entities import Season
        from src.modules.media.domain.value_objects import AirDate, SeriesId

        air_date = AirDate(date(2024, 1, 15))
        season = Season(
            series_id=SeriesId.generate(),
            season_number=1,
            air_date=air_date,
        )

        assert season.air_date == air_date


class TestSeasonEpisodeManagement:
    """Tests for Season episode management."""

    def test_episode_count_should_return_zero_when_empty(self):
        from src.modules.media.domain.entities import Season
        from src.modules.media.domain.value_objects import SeriesId

        season = Season(
            series_id=SeriesId.generate(),
            season_number=1,
        )

        assert season.episode_count == 0

    def test_should_add_episode(self):
        from src.modules.media.domain.entities import Season
        from src.modules.media.domain.value_objects import SeriesId

        series_id = SeriesId.generate()
        season = Season(
            series_id=series_id,
            season_number=1,
        )

        episode = _make_episode(series_id, season_number=1, episode_number=1)
        season = season.with_episode(episode)

        assert season.episode_count == 1
        assert season.episodes[0] == episode

    def test_should_raise_error_when_adding_episode_with_wrong_series_id(self):
        from src.modules.media.domain.entities import Season
        from src.modules.media.domain.value_objects import SeriesId

        season = Season(
            series_id=SeriesId.generate(),
            season_number=1,
        )

        episode = _make_episode(SeriesId.generate(), season_number=1)

        with pytest.raises(BusinessRuleViolationException, match="series_id"):
            season.with_episode(episode)

    def test_should_raise_error_when_adding_episode_with_wrong_season_number(self):
        from src.modules.media.domain.entities import Season
        from src.modules.media.domain.value_objects import SeriesId

        series_id = SeriesId.generate()
        season = Season(
            series_id=series_id,
            season_number=1,
        )

        episode = _make_episode(series_id, season_number=2)

        with pytest.raises(BusinessRuleViolationException, match="season_number"):
            season.with_episode(episode)

    def test_should_get_episode_by_number(self):
        from src.modules.media.domain.entities import Season
        from src.modules.media.domain.value_objects import SeriesId

        series_id = SeriesId.generate()
        season = Season(
            series_id=series_id,
            season_number=1,
        )

        episode = _make_episode(series_id, season_number=1, episode_number=5)
        season = season.with_episode(episode)

        found = season.get_episode(5)
        assert found == episode

    def test_should_return_none_when_episode_not_found(self):
        from src.modules.media.domain.entities import Season
        from src.modules.media.domain.value_objects import SeriesId

        season = Season(
            series_id=SeriesId.generate(),
            season_number=1,
        )

        found = season.get_episode(99)
        assert found is None


class TestSeasonEquality:
    """Tests for Season equality based on ID."""

    def test_should_be_equal_when_same_id(self):
        from src.modules.media.domain.entities import Season
        from src.modules.media.domain.value_objects import SeasonId, SeriesId

        season_id = SeasonId.generate()
        series_id = SeriesId.generate()

        season1 = Season(id=season_id, series_id=series_id, season_number=1)
        season2 = Season(id=season_id, series_id=series_id, season_number=1)

        assert season1 == season2

    def test_should_not_be_equal_when_different_id(self):
        from src.modules.media.domain.entities import Season
        from src.modules.media.domain.value_objects import SeasonId, SeriesId

        series_id = SeriesId.generate()

        season1 = Season(id=SeasonId.generate(), series_id=series_id, season_number=1)
        season2 = Season(id=SeasonId.generate(), series_id=series_id, season_number=1)

        assert season1 != season2


class TestSeasonImmutability:
    """Tests for Season frozen (immutable) behavior."""

    def test_should_reject_direct_attribute_assignment(self):
        from src.modules.media.domain.entities import Season
        from src.modules.media.domain.value_objects import SeriesId

        season = Season(
            series_id=SeriesId.generate(),
            season_number=1,
        )

        with pytest.raises(DomainValidationException):
            season.season_number = 2  # type: ignore[misc]

    def test_with_episode_should_return_new_instance(self):
        from src.modules.media.domain.entities import Season
        from src.modules.media.domain.value_objects import SeriesId

        series_id = SeriesId.generate()
        season = Season(
            series_id=series_id,
            season_number=1,
        )

        episode = _make_episode(series_id, season_number=1)
        updated = season.with_episode(episode)

        assert updated is not season
        assert updated.episode_count == 1
        assert season.episode_count == 0

    def test_with_episode_should_preserve_identity(self):
        from src.modules.media.domain.entities import Season
        from src.modules.media.domain.value_objects import SeasonId, SeriesId

        series_id = SeriesId.generate()
        season = Season(
            id=SeasonId.generate(),
            series_id=series_id,
            season_number=1,
        )

        episode = _make_episode(series_id, season_number=1)
        updated = season.with_episode(episode)

        assert updated == season  # same id

    def test_with_episode_duplicate_should_return_self(self):
        from src.modules.media.domain.entities import Season
        from src.modules.media.domain.value_objects import SeriesId

        series_id = SeriesId.generate()
        season = Season(
            series_id=series_id,
            season_number=1,
        )

        episode = _make_episode(series_id, season_number=1)
        season = season.with_episode(episode)

        result = season.with_episode(episode)

        assert result is season
