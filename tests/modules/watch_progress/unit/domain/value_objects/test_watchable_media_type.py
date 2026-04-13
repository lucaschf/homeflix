"""Tests for WatchableMediaType enum."""

import pytest


class TestWatchableMediaTypeValues:
    """Tests for WatchableMediaType enum members."""

    def test_should_have_movie_member(self):
        from src.modules.watch_progress.domain.value_objects import WatchableMediaType

        assert WatchableMediaType.MOVIE.value == "movie"

    def test_should_have_episode_member(self):
        from src.modules.watch_progress.domain.value_objects import WatchableMediaType

        assert WatchableMediaType.EPISODE.value == "episode"

    def test_should_construct_from_string(self):
        from src.modules.watch_progress.domain.value_objects import WatchableMediaType

        assert WatchableMediaType("movie") == WatchableMediaType.MOVIE
        assert WatchableMediaType("episode") == WatchableMediaType.EPISODE

    def test_should_raise_for_invalid_value(self):
        from src.modules.watch_progress.domain.value_objects import WatchableMediaType

        with pytest.raises(ValueError):
            WatchableMediaType("invalid")

    def test_should_behave_as_string(self):
        """StrEnum inherits from str, so string comparisons work."""
        from src.modules.watch_progress.domain.value_objects import WatchableMediaType

        assert WatchableMediaType.MOVIE.value == "movie"
        assert isinstance(WatchableMediaType.MOVIE, str)
