"""Tests for Episode entity."""

from datetime import date

import pytest

from src.building_blocks.domain.errors import DomainValidationException
from src.modules.media.domain.value_objects import FilePath, MediaFile, Resolution


def _make_file(**overrides: object) -> MediaFile:
    """Create a MediaFile for testing."""
    defaults: dict[str, object] = {
        "file_path": FilePath("/series/show/s01e01.mkv"),
        "file_size": 1_000_000_000,
        "resolution": Resolution("1080p"),
        "is_primary": True,
    }
    defaults.update(overrides)
    return MediaFile(**defaults)


class TestEpisodeCreation:
    """Tests for Episode instantiation."""

    def test_should_create_with_required_fields(self):
        from src.modules.media.domain.entities import Episode
        from src.modules.media.domain.value_objects import (
            Duration,
            SeriesId,
            Title,
        )

        episode = Episode(
            series_id=SeriesId.generate(),
            season_number=1,
            episode_number=1,
            title=Title("Pilot"),
            duration=Duration(2700),
            files=[_make_file()],
        )

        assert episode.id is None
        assert episode.episode_number == 1
        assert episode.title.value == "Pilot"

    def test_should_create_with_explicit_id(self):
        from src.modules.media.domain.entities import Episode
        from src.modules.media.domain.value_objects import (
            Duration,
            EpisodeId,
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
            files=[_make_file()],
        )

        assert episode.id == episode_id

    def test_should_accept_string_id_and_convert(self):
        from src.modules.media.domain.entities import Episode
        from src.modules.media.domain.value_objects import (
            Duration,
            EpisodeId,
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
            files=[_make_file()],
        )

        assert isinstance(episode.id, EpisodeId)
        assert episode.id.value == "epi_abc123abc123"

    def test_should_allow_season_number_zero_for_specials(self):
        from src.modules.media.domain.entities import Episode
        from src.modules.media.domain.value_objects import (
            Duration,
            FilePath,
            MediaFile,
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
            files=[
                MediaFile(
                    file_path=FilePath("/series/show/s00e01.mkv"),
                    file_size=1_000_000_000,
                    resolution=Resolution("1080p"),
                    is_primary=True,
                )
            ],
        )

        assert episode.season_number == 0

    def test_should_raise_error_for_negative_episode_number(self):
        from src.modules.media.domain.entities import Episode
        from src.modules.media.domain.value_objects import (
            Duration,
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
                files=[_make_file()],
            )

    def test_should_create_with_no_files(self):
        from src.modules.media.domain.entities import Episode
        from src.modules.media.domain.value_objects import (
            Duration,
            SeriesId,
            Title,
        )

        episode = Episode(
            series_id=SeriesId.generate(),
            season_number=1,
            episode_number=1,
            title=Title("Pilot"),
            duration=Duration(2700),
        )

        assert episode.files == []


class TestEpisodeOptionalFields:
    """Tests for Episode optional fields."""

    def test_should_create_with_synopsis(self):
        from src.modules.media.domain.entities import Episode
        from src.modules.media.domain.value_objects import (
            Duration,
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
            files=[_make_file()],
        )

        assert episode.synopsis == "The first episode of the series."

    def test_should_create_with_thumbnail_path(self):
        from src.modules.media.domain.entities import Episode
        from src.modules.media.domain.value_objects import (
            Duration,
            FilePath,
            SeriesId,
            Title,
        )

        episode = Episode(
            series_id=SeriesId.generate(),
            season_number=1,
            episode_number=1,
            title=Title("Pilot"),
            duration=Duration(2700),
            files=[_make_file()],
            thumbnail_path=FilePath("/thumbnails/show/s01e01.jpg"),
        )

        assert episode.thumbnail_path is not None

    def test_should_create_with_air_date(self):
        from src.modules.media.domain.entities import Episode
        from src.modules.media.domain.value_objects import (
            Duration,
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
            files=[_make_file()],
            air_date=air_date,
        )

        assert episode.air_date == air_date


class TestEpisodeFileManagement:
    """Tests for Episode file variant management."""

    def test_primary_file_should_return_primary(self):
        from src.modules.media.domain.entities import Episode
        from src.modules.media.domain.value_objects import Duration, SeriesId, Title

        episode = Episode(
            series_id=SeriesId.generate(),
            season_number=1,
            episode_number=1,
            title=Title("Pilot"),
            duration=Duration(2700),
            files=[_make_file()],
        )

        assert episode.primary_file is not None
        assert episode.primary_file.is_primary is True

    def test_with_file_should_add_new_variant(self):
        from src.modules.media.domain.entities import Episode
        from src.modules.media.domain.value_objects import (
            Duration,
            FilePath,
            MediaFile,
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
            files=[_make_file()],
        )

        episode = episode.with_file(
            MediaFile(
                file_path=FilePath("/series/show/s01e01_4k.mkv"),
                file_size=3_000_000_000,
                resolution=Resolution("4K"),
            )
        )

        assert len(episode.files) == 2

    def test_best_file_should_return_highest_resolution(self):
        from src.modules.media.domain.entities import Episode
        from src.modules.media.domain.value_objects import (
            Duration,
            FilePath,
            MediaFile,
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
            files=[_make_file(resolution=Resolution("720p"))],
        )
        episode = episode.with_file(
            MediaFile(
                file_path=FilePath("/series/show/s01e01_4k.mkv"),
                file_size=3_000_000_000,
                resolution=Resolution("4K"),
            )
        )

        assert episode.best_file is not None
        assert episode.best_file.resolution.name == "4K"


class TestEpisodeEquality:
    """Tests for Episode equality based on ID."""

    def test_should_be_equal_when_same_id(self):
        from src.modules.media.domain.entities import Episode
        from src.modules.media.domain.value_objects import (
            Duration,
            EpisodeId,
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
            files=[_make_file()],
        )

        episode2 = Episode(
            id=episode_id,
            series_id=series_id,
            season_number=1,
            episode_number=1,
            title=Title("Different Title"),
            duration=Duration(3000),
            files=[_make_file()],
        )

        assert episode1 == episode2

    def test_should_not_be_equal_when_different_id(self):
        from src.modules.media.domain.entities import Episode
        from src.modules.media.domain.value_objects import (
            Duration,
            EpisodeId,
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
            files=[_make_file()],
        )

        episode2 = Episode(
            id=EpisodeId.generate(),
            series_id=series_id,
            season_number=1,
            episode_number=1,
            title=Title("Pilot"),
            duration=Duration(2700),
            files=[_make_file()],
        )

        assert episode1 != episode2


class TestEpisodeTimestamps:
    """Tests for Episode timestamp management."""

    def test_should_have_created_at_on_creation(self):
        from src.modules.media.domain.entities import Episode
        from src.modules.media.domain.value_objects import (
            Duration,
            SeriesId,
            Title,
        )

        episode = Episode(
            series_id=SeriesId.generate(),
            season_number=1,
            episode_number=1,
            title=Title("Pilot"),
            duration=Duration(2700),
            files=[_make_file()],
        )

        assert episode.created_at is not None

    def test_should_reject_direct_attribute_assignment(self):
        from src.modules.media.domain.entities import Episode
        from src.modules.media.domain.value_objects import (
            Duration,
            SeriesId,
            Title,
        )

        episode = Episode(
            series_id=SeriesId.generate(),
            season_number=1,
            episode_number=1,
            title=Title("Pilot"),
            duration=Duration(2700),
            files=[_make_file()],
        )

        with pytest.raises(DomainValidationException):
            episode.season_number = 2  # type: ignore[misc]
