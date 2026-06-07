"""Tests for the WatchableMediaId value object."""

import pytest

from src.building_blocks.domain.errors import DomainValidationException
from src.modules.watch_progress.domain.value_objects import WatchableMediaId
from src.shared_kernel.value_objects.media_id import MovieId


class TestWatchableMediaIdMovie:
    """Movie-shaped ids."""

    def test_accepts_valid_movie_id(self):
        media_id = WatchableMediaId("mov_2xK9mPqR7nL4")

        assert media_id.value == "mov_2xK9mPqR7nL4"
        assert media_id.is_movie is True
        assert media_id.is_episode is False

    def test_as_movie_id_returns_typed_id(self):
        media_id = WatchableMediaId("mov_2xK9mPqR7nL4")

        assert media_id.as_movie_id() == MovieId("mov_2xK9mPqR7nL4")

    def test_rejects_malformed_movie_id(self):
        with pytest.raises(DomainValidationException):
            WatchableMediaId("mov_short")


class TestWatchableMediaIdEpisode:
    """Composite-episode-shaped ids."""

    def test_accepts_valid_composite_id(self):
        media_id = WatchableMediaId("epi_ser_3yL8nQsT9mK5_3_2")

        assert media_id.is_episode is True
        assert media_id.is_movie is False

    def test_as_episode_parses_components(self):
        parsed = WatchableMediaId("epi_ser_3yL8nQsT9mK5_3_2").as_episode()

        assert parsed.series_id == "ser_3yL8nQsT9mK5"
        assert parsed.season_number == 3
        assert parsed.episode_number == 2

    def test_rejects_plain_catalog_episode_id(self):
        # The player only ever sends composite ids; a bare epi_xxx would
        # be invisible to Continue Watching, so it fails at the boundary.
        with pytest.raises(DomainValidationException):
            WatchableMediaId("epi_5aH0pQuV1oM7")

    def test_rejects_composite_with_invalid_series_id(self):
        with pytest.raises(DomainValidationException):
            WatchableMediaId("epi_ser_bad_1_2")

    def test_as_episode_raises_for_movie_id(self):
        with pytest.raises(ValueError, match="Not a composite episode id"):
            WatchableMediaId("mov_2xK9mPqR7nL4").as_episode()


class TestWatchableMediaIdRejections:
    """Garbage shapes."""

    @pytest.mark.parametrize(
        "value",
        [
            "",
            "garbage",
            "ser_3yL8nQsT9mK5",
            "ssn_4zM9oPtU0nL6",
            "lib_2xK9mPqR7nL4",
            "epi_ser_3yL8nQsT9mK5_x_y",
        ],
    )
    def test_rejects_invalid_shapes(self, value: str):
        with pytest.raises(DomainValidationException):
            WatchableMediaId(value)
