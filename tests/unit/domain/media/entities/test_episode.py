"""Tests for Episode entity."""

from datetime import date

import pytest

from src.domain.shared.exceptions.domain import DomainValidationException


class TestEpisodeCreation:
    """Tests for Episode instantiation."""

    def test_should_create_with_required_fields(self):
        from src.domain.media.entities import Episode
        from src.domain.media.value_objects import (
            Duration,
            FilePath,
            Resolution,
            SeriesId,
            Title,
        )

        episode = Episode(
            series_id=SeriesId.generate(),
            season_number=1,
            episode_number=1,
            title=Title("Pilot"),
            duration=Duration(2700),
            file_path=FilePath("/series/show/s01e01.mkv"),
            file_size=1_000_000_000,
            resolution=Resolution("1080p"),
        )

        assert episode.id is None
        assert episode.episode_number == 1
        assert episode.title.value == "Pilot"

    def test_should_create_with_explicit_id(self):
        from src.domain.media.entities import Episode
        from src.domain.media.value_objects import (
            Duration,
            EpisodeId,
            FilePath,
            Resolution,
            SeriesId,
            Title,
        )

        episode_id = EpisodeId.generate()
        episode = Episode(
            id=episode_id,
            series_id=SeriesId.generate(),
            season_number=1,
            episode_number=1,
            title=Title("Pilot"),
            duration=Duration(2700),
            file_path=FilePath("/series/show/s01e01.mkv"),
            file_size=1_000_000_000,
            resolution=Resolution("1080p"),
        )

        assert episode.id == episode_id

    def test_should_accept_string_id_and_convert(self):
        from src.domain.media.entities import Episode
        from src.domain.media.value_objects import (
            Duration,
            EpisodeId,
            FilePath,
            Resolution,
            SeriesId,
            Title,
        )

        episode = Episode(
            id="epi_abc123abc123",
            series_id=SeriesId.generate(),
            season_number=1,
            episode_number=1,
            title=Title("Pilot"),
            duration=Duration(2700),
            file_path=FilePath("/series/show/s01e01.mkv"),
            file_size=1_000_000_000,
            resolution=Resolution("1080p"),
        )

        assert isinstance(episode.id, EpisodeId)
        assert episode.id.value == "epi_abc123abc123"

    def test_should_allow_season_number_zero_for_specials(self):
        from src.domain.media.entities import Episode
        from src.domain.media.value_objects import (
            Duration,
            FilePath,
            Resolution,
            SeriesId,
            Title,
        )

        episode = Episode(
            series_id=SeriesId.generate(),
            season_number=0,
            episode_number=1,
            title=Title("Special Episode"),
            duration=Duration(2700),
            file_path=FilePath("/series/show/s00e01.mkv"),
            file_size=1_000_000_000,
            resolution=Resolution("1080p"),
        )

        assert episode.season_number == 0

    def test_should_raise_error_for_negative_episode_number(self):
        from src.domain.media.entities import Episode
        from src.domain.media.value_objects import (
            Duration,
            FilePath,
            Resolution,
            SeriesId,
            Title,
        )

        with pytest.raises(DomainValidationException):
            Episode(
                series_id=SeriesId.generate(),
                season_number=1,
                episode_number=0,
                title=Title("Pilot"),
                duration=Duration(2700),
                file_path=FilePath("/series/show/s01e00.mkv"),
                file_size=1_000_000_000,
                resolution=Resolution("1080p"),
            )

    def test_should_raise_error_for_negative_file_size(self):
        from src.domain.media.entities import Episode
        from src.domain.media.value_objects import (
            Duration,
            FilePath,
            Resolution,
            SeriesId,
            Title,
        )

        with pytest.raises(DomainValidationException):
            Episode(
                series_id=SeriesId.generate(),
                season_number=1,
                episode_number=1,
                title=Title("Pilot"),
                duration=Duration(2700),
                file_path=FilePath("/series/show/s01e01.mkv"),
                file_size=-1,
                resolution=Resolution("1080p"),
            )


class TestEpisodeOptionalFields:
    """Tests for Episode optional fields."""

    def test_should_create_with_synopsis(self):
        from src.domain.media.entities import Episode
        from src.domain.media.value_objects import (
            Duration,
            FilePath,
            Resolution,
            SeriesId,
            Title,
        )

        episode = Episode(
            series_id=SeriesId.generate(),
            season_number=1,
            episode_number=1,
            title=Title("Pilot"),
            synopsis="The first episode of the series.",
            duration=Duration(2700),
            file_path=FilePath("/series/show/s01e01.mkv"),
            file_size=1_000_000_000,
            resolution=Resolution("1080p"),
        )

        assert episode.synopsis == "The first episode of the series."

    def test_should_create_with_thumbnail_path(self):
        from src.domain.media.entities import Episode
        from src.domain.media.value_objects import (
            Duration,
            FilePath,
            Resolution,
            SeriesId,
            Title,
        )

        episode = Episode(
            series_id=SeriesId.generate(),
            season_number=1,
            episode_number=1,
            title=Title("Pilot"),
            duration=Duration(2700),
            file_path=FilePath("/series/show/s01e01.mkv"),
            file_size=1_000_000_000,
            resolution=Resolution("1080p"),
            thumbnail_path=FilePath("/thumbnails/show/s01e01.jpg"),
        )

        assert episode.thumbnail_path is not None

    def test_should_create_with_air_date(self):
        from src.domain.media.entities import Episode
        from src.domain.media.value_objects import (
            Duration,
            FilePath,
            Resolution,
            SeriesId,
            Title,
        )

        air_date = date(2024, 1, 15)
        episode = Episode(
            series_id=SeriesId.generate(),
            season_number=1,
            episode_number=1,
            title=Title("Pilot"),
            duration=Duration(2700),
            file_path=FilePath("/series/show/s01e01.mkv"),
            file_size=1_000_000_000,
            resolution=Resolution("1080p"),
            air_date=air_date,
        )

        assert episode.air_date == air_date


class TestEpisodeEquality:
    """Tests for Episode equality based on ID."""

    def test_should_be_equal_when_same_id(self):
        from src.domain.media.entities import Episode
        from src.domain.media.value_objects import (
            Duration,
            EpisodeId,
            FilePath,
            Resolution,
            SeriesId,
            Title,
        )

        episode_id = EpisodeId.generate()
        series_id = SeriesId.generate()

        episode1 = Episode(
            id=episode_id,
            series_id=series_id,
            season_number=1,
            episode_number=1,
            title=Title("Pilot"),
            duration=Duration(2700),
            file_path=FilePath("/series/show/s01e01.mkv"),
            file_size=1_000_000_000,
            resolution=Resolution("1080p"),
        )

        episode2 = Episode(
            id=episode_id,
            series_id=series_id,
            season_number=1,
            episode_number=1,
            title=Title("Different Title"),
            duration=Duration(3000),
            file_path=FilePath("/series/show/s01e01.mkv"),
            file_size=1_000_000_000,
            resolution=Resolution("1080p"),
        )

        assert episode1 == episode2

    def test_should_not_be_equal_when_different_id(self):
        from src.domain.media.entities import Episode
        from src.domain.media.value_objects import (
            Duration,
            EpisodeId,
            FilePath,
            Resolution,
            SeriesId,
            Title,
        )

        series_id = SeriesId.generate()

        episode1 = Episode(
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

        episode2 = Episode(
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

        assert episode1 != episode2


class TestEpisodeTimestamps:
    """Tests for Episode timestamp management."""

    def test_should_have_created_at_on_creation(self):
        from src.domain.media.entities import Episode
        from src.domain.media.value_objects import (
            Duration,
            FilePath,
            Resolution,
            SeriesId,
            Title,
        )

        episode = Episode(
            series_id=SeriesId.generate(),
            season_number=1,
            episode_number=1,
            title=Title("Pilot"),
            duration=Duration(2700),
            file_path=FilePath("/series/show/s01e01.mkv"),
            file_size=1_000_000_000,
            resolution=Resolution("1080p"),
        )

        assert episode.created_at is not None

    def test_should_update_timestamp_on_touch(self):
        from datetime import UTC, datetime

        from src.domain.media.entities import Episode
        from src.domain.media.value_objects import (
            Duration,
            FilePath,
            Resolution,
            SeriesId,
            Title,
        )

        episode = Episode(
            series_id=SeriesId.generate(),
            season_number=1,
            episode_number=1,
            title=Title("Pilot"),
            duration=Duration(2700),
            file_path=FilePath("/series/show/s01e01.mkv"),
            file_size=1_000_000_000,
            resolution=Resolution("1080p"),
            updated_at=datetime(2020, 1, 1, tzinfo=UTC),
        )

        old_updated_at = episode.updated_at
        episode.touch()

        assert episode.updated_at > old_updated_at
