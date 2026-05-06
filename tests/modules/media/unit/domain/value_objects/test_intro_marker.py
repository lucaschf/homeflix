"""Tests for IntroMarker value object."""

from datetime import UTC, datetime

import pytest

from src.building_blocks.domain.errors import DomainValidationException
from src.modules.media.domain.value_objects import IntroMarker, IntroMarkerSource


class TestIntroMarkerCreation:
    """Tests for IntroMarker instantiation."""

    def test_should_create_auto_detected_marker(self):
        marker = IntroMarker(
            start_seconds=12,
            end_seconds=98,
            source=IntroMarkerSource.AUTO_DETECTED,
            confidence=0.92,
        )

        assert marker.start_seconds == 12
        assert marker.end_seconds == 98
        assert marker.source == IntroMarkerSource.AUTO_DETECTED
        assert marker.confidence == 0.92
        assert marker.detected_at is not None

    def test_should_create_manual_marker_without_confidence(self):
        marker = IntroMarker(
            start_seconds=0,
            end_seconds=60,
            source=IntroMarkerSource.MANUAL,
        )

        assert marker.source == IntroMarkerSource.MANUAL
        assert marker.confidence is None

    def test_should_accept_explicit_detected_at(self):
        ts = datetime(2026, 4, 1, 12, 0, tzinfo=UTC)
        marker = IntroMarker(
            start_seconds=10,
            end_seconds=50,
            source=IntroMarkerSource.MANUAL,
            detected_at=ts,
        )

        assert marker.detected_at == ts


class TestIntroMarkerValidation:
    """Tests for IntroMarker invariant enforcement."""

    def test_should_raise_when_end_equals_start(self):
        with pytest.raises(DomainValidationException):
            IntroMarker(
                start_seconds=30,
                end_seconds=30,
                source=IntroMarkerSource.MANUAL,
            )

    def test_should_raise_when_end_before_start(self):
        with pytest.raises(DomainValidationException):
            IntroMarker(
                start_seconds=60,
                end_seconds=30,
                source=IntroMarkerSource.MANUAL,
            )

    def test_should_raise_when_start_negative(self):
        with pytest.raises(DomainValidationException):
            IntroMarker(
                start_seconds=-1,
                end_seconds=30,
                source=IntroMarkerSource.MANUAL,
            )

    def test_should_raise_when_confidence_above_one(self):
        with pytest.raises(DomainValidationException):
            IntroMarker(
                start_seconds=0,
                end_seconds=60,
                source=IntroMarkerSource.AUTO_DETECTED,
                confidence=1.5,
            )

    def test_should_raise_when_confidence_negative(self):
        with pytest.raises(DomainValidationException):
            IntroMarker(
                start_seconds=0,
                end_seconds=60,
                source=IntroMarkerSource.AUTO_DETECTED,
                confidence=-0.1,
            )

    def test_should_raise_when_auto_detected_without_confidence(self):
        with pytest.raises(DomainValidationException):
            IntroMarker(
                start_seconds=0,
                end_seconds=60,
                source=IntroMarkerSource.AUTO_DETECTED,
            )

    def test_should_raise_when_manual_with_confidence(self):
        with pytest.raises(DomainValidationException):
            IntroMarker(
                start_seconds=0,
                end_seconds=60,
                source=IntroMarkerSource.MANUAL,
                confidence=0.5,
            )


class TestIntroMarkerProperties:
    """Tests for IntroMarker computed properties."""

    def test_duration_seconds_should_return_difference(self):
        marker = IntroMarker(
            start_seconds=15,
            end_seconds=95,
            source=IntroMarkerSource.MANUAL,
        )

        assert marker.duration_seconds == 80

    def test_is_manual_should_be_true_for_manual_source(self):
        marker = IntroMarker(
            start_seconds=0,
            end_seconds=60,
            source=IntroMarkerSource.MANUAL,
        )

        assert marker.is_manual is True

    def test_is_manual_should_be_false_for_auto_source(self):
        marker = IntroMarker(
            start_seconds=0,
            end_seconds=60,
            source=IntroMarkerSource.AUTO_DETECTED,
            confidence=0.8,
        )

        assert marker.is_manual is False


class TestIntroMarkerImmutability:
    """Tests for IntroMarker immutability and equality."""

    def test_should_be_immutable(self):
        marker = IntroMarker(
            start_seconds=0,
            end_seconds=60,
            source=IntroMarkerSource.MANUAL,
        )

        with pytest.raises(DomainValidationException):
            marker.start_seconds = 10  # type: ignore[misc]

    def test_with_updates_should_return_new_instance(self):
        original = IntroMarker(
            start_seconds=0,
            end_seconds=60,
            source=IntroMarkerSource.AUTO_DETECTED,
            confidence=0.7,
        )

        updated = original.with_updates(confidence=0.95)

        assert updated.confidence == 0.95
        assert original.confidence == 0.7  # original untouched
        assert updated is not original

    def test_with_updates_should_preserve_invariants(self):
        marker = IntroMarker(
            start_seconds=10,
            end_seconds=60,
            source=IntroMarkerSource.MANUAL,
        )

        with pytest.raises(DomainValidationException):
            marker.with_updates(end_seconds=5)

    def test_should_be_equal_with_same_values(self):
        ts = datetime(2026, 4, 1, 12, 0, tzinfo=UTC)
        kwargs = {
            "start_seconds": 10,
            "end_seconds": 60,
            "source": IntroMarkerSource.MANUAL,
            "detected_at": ts,
        }

        m1 = IntroMarker(**kwargs)
        m2 = IntroMarker(**kwargs)

        assert m1 == m2
