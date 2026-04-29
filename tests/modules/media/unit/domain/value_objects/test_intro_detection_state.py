"""Tests for IntroDetectionState enum."""

from src.modules.media.domain.value_objects import IntroDetectionState


class TestIntroDetectionState:
    """Tests for the IntroDetectionState enum values."""

    def test_should_expose_all_expected_states(self):
        assert IntroDetectionState.NOT_STARTED.value == "NOT_STARTED"
        assert IntroDetectionState.IN_PROGRESS.value == "IN_PROGRESS"
        assert IntroDetectionState.COMPLETED.value == "COMPLETED"
        assert IntroDetectionState.FAILED.value == "FAILED"
        assert IntroDetectionState.INSUFFICIENT_EPISODES.value == "INSUFFICIENT_EPISODES"
        assert IntroDetectionState.DISABLED.value == "DISABLED"

    def test_should_be_string_comparable(self):
        # StrEnum allows equality with raw strings — useful for storing
        # the value in a database column without manual coercion.
        assert IntroDetectionState.COMPLETED == "COMPLETED"
        assert IntroDetectionState("FAILED") is IntroDetectionState.FAILED
