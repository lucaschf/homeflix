"""Tests for the PlaybackPosition value object."""

import pytest

from src.building_blocks.domain.errors import DomainValidationException
from src.modules.watch_progress.domain.value_objects import PlaybackPosition


@pytest.mark.unit
class TestPlaybackPositionValidation:
    """Invariants enforced at construction."""

    def test_accepts_zero_position(self) -> None:
        assert PlaybackPosition(position_seconds=0, duration_seconds=7200).position_seconds == 0

    def test_rejects_negative_position(self) -> None:
        with pytest.raises(DomainValidationException):
            PlaybackPosition(position_seconds=-1, duration_seconds=7200)

    def test_rejects_zero_duration(self) -> None:
        with pytest.raises(DomainValidationException):
            PlaybackPosition(position_seconds=10, duration_seconds=0)

    def test_allows_position_beyond_duration(self) -> None:
        # A stale-duration report can momentarily exceed the total; the VO
        # accepts it and the percentage clamps rather than rejecting.
        pos = PlaybackPosition(position_seconds=9000, duration_seconds=7200)
        assert pos.percentage == 100.0


@pytest.mark.unit
class TestPlaybackPositionMath:
    """Ratio / percentage / completion arithmetic lives on the VO."""

    def test_ratio_is_unclamped(self) -> None:
        assert PlaybackPosition(position_seconds=3600, duration_seconds=7200).ratio == 0.5

    def test_percentage_half(self) -> None:
        assert PlaybackPosition(position_seconds=3600, duration_seconds=7200).percentage == 50.0

    def test_percentage_clamped_to_100(self) -> None:
        assert PlaybackPosition(position_seconds=8000, duration_seconds=7200).percentage == 100.0

    def test_reaches_completion_at_threshold(self) -> None:
        pos = PlaybackPosition(position_seconds=6480, duration_seconds=7200)  # 0.9
        assert pos.reaches_completion(0.9) is True

    def test_below_threshold_is_not_complete(self) -> None:
        pos = PlaybackPosition(position_seconds=6479, duration_seconds=7200)
        assert pos.reaches_completion(0.9) is False

    def test_equality_by_value(self) -> None:
        a = PlaybackPosition(position_seconds=100, duration_seconds=200)
        b = PlaybackPosition(position_seconds=100, duration_seconds=200)
        assert a == b
