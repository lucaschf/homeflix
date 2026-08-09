"""Tests for FileSegment value object (ADR-030)."""

import pytest

from src.building_blocks.domain.errors import DomainValidationException
from src.modules.media.domain.value_objects import FileSegment


class TestFileSegmentCreation:
    """Tests for FileSegment instantiation."""

    def test_should_create_valid_segment(self):
        segment = FileSegment(start_seconds=4740, end_seconds=9480)

        assert segment.start_seconds == 4740
        assert segment.end_seconds == 9480

    def test_should_allow_segment_starting_at_zero(self):
        segment = FileSegment(start_seconds=0, end_seconds=4740)

        assert segment.start_seconds == 0
        assert segment.end_seconds == 4740


class TestFileSegmentValidation:
    """Tests for FileSegment invariant enforcement."""

    def test_should_raise_when_end_equals_start(self):
        with pytest.raises(DomainValidationException):
            FileSegment(start_seconds=100, end_seconds=100)

    def test_should_raise_when_end_before_start(self):
        with pytest.raises(DomainValidationException):
            FileSegment(start_seconds=200, end_seconds=100)

    def test_should_raise_when_start_negative(self):
        with pytest.raises(DomainValidationException):
            FileSegment(start_seconds=-1, end_seconds=100)


class TestFileSegmentProperties:
    """Tests for FileSegment computed properties."""

    def test_duration_seconds_should_return_difference(self):
        segment = FileSegment(start_seconds=4740, end_seconds=9480)

        assert segment.duration_seconds == 4740


class TestFileSegmentImmutability:
    """Tests for FileSegment immutability and equality."""

    def test_should_be_immutable(self):
        segment = FileSegment(start_seconds=0, end_seconds=60)

        with pytest.raises(DomainValidationException):
            segment.start_seconds = 10  # type: ignore[misc]

    def test_with_updates_should_preserve_invariants(self):
        segment = FileSegment(start_seconds=10, end_seconds=60)

        with pytest.raises(DomainValidationException):
            segment.with_updates(end_seconds=5)

    def test_should_be_equal_with_same_values(self):
        s1 = FileSegment(start_seconds=10, end_seconds=60)
        s2 = FileSegment(start_seconds=10, end_seconds=60)

        assert s1 == s2
