"""Tests for WatchStatus enum."""

import pytest


class TestWatchStatusValues:
    """Tests for WatchStatus enum members."""

    def test_should_have_in_progress_member(self):
        from src.modules.watch_progress.domain.value_objects import WatchStatus

        assert WatchStatus.IN_PROGRESS.value == "in_progress"

    def test_should_have_completed_member(self):
        from src.modules.watch_progress.domain.value_objects import WatchStatus

        assert WatchStatus.COMPLETED.value == "completed"

    def test_should_construct_from_string(self):
        from src.modules.watch_progress.domain.value_objects import WatchStatus

        assert WatchStatus("in_progress") == WatchStatus.IN_PROGRESS
        assert WatchStatus("completed") == WatchStatus.COMPLETED

    def test_should_raise_for_invalid_value(self):
        from src.modules.watch_progress.domain.value_objects import WatchStatus

        with pytest.raises(ValueError):
            WatchStatus("invalid")

    def test_should_behave_as_string(self):
        """StrEnum inherits from str, so string comparisons work."""
        from src.modules.watch_progress.domain.value_objects import WatchStatus

        assert WatchStatus.IN_PROGRESS.value == "in_progress"
        assert isinstance(WatchStatus.IN_PROGRESS, str)
