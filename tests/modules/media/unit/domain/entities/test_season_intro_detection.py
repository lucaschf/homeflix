"""Tests for Season intro-detection state transitions."""

from datetime import UTC, datetime

import pytest

from src.building_blocks.domain.errors import BusinessRuleViolationException
from src.modules.media.domain.entities import Season
from src.modules.media.domain.rule_codes import MediaRuleCodes
from src.modules.media.domain.value_objects import (
    IntroDetectionState,
    SeriesId,
)


def _make_season() -> Season:
    return Season(
        series_id=SeriesId.generate(),
        season_number=1,
    )


class TestSeasonDetectionDefaults:
    """Tests for the default state on a freshly-built Season."""

    def test_should_default_to_not_started(self):
        season = _make_season()

        assert season.intro_detection_state == IntroDetectionState.NOT_STARTED
        assert season.intro_detection_attempted_at is None
        assert season.intro_detection_error is None


class TestWithDetectionStarted:
    """Tests for Season.with_detection_started."""

    def test_should_transition_from_not_started(self):
        season = _make_season()

        started = season.with_detection_started()

        assert started.intro_detection_state == IntroDetectionState.IN_PROGRESS
        assert started.intro_detection_error is None

    def test_should_clear_previous_error_when_retrying_after_failure(self):
        season = _make_season().with_detection_failed("ffmpeg crashed")

        started = season.with_detection_started()

        assert started.intro_detection_state == IntroDetectionState.IN_PROGRESS
        assert started.intro_detection_error is None

    def test_should_raise_when_already_in_progress(self):
        season = _make_season().with_detection_started()

        with pytest.raises(BusinessRuleViolationException) as exc_info:
            season.with_detection_started()

        assert exc_info.value.rule_code == MediaRuleCodes.INTRO_DETECTION_INVALID_TRANSITION

    def test_should_raise_when_disabled(self):
        season = _make_season().with_detection_disabled()

        with pytest.raises(BusinessRuleViolationException) as exc_info:
            season.with_detection_started()

        assert exc_info.value.rule_code == MediaRuleCodes.INTRO_DETECTION_INVALID_TRANSITION

    def test_should_allow_rerun_after_completion(self):
        season = _make_season().with_detection_started().with_detection_completed()

        rerun = season.with_detection_started()

        assert rerun.intro_detection_state == IntroDetectionState.IN_PROGRESS


class TestWithDetectionCompleted:
    """Tests for Season.with_detection_completed."""

    def test_should_transition_to_completed(self):
        season = _make_season().with_detection_started()

        completed = season.with_detection_completed()

        assert completed.intro_detection_state == IntroDetectionState.COMPLETED
        assert completed.intro_detection_attempted_at is not None
        assert completed.intro_detection_error is None

    def test_should_use_explicit_attempted_at(self):
        season = _make_season().with_detection_started()
        ts = datetime(2026, 4, 1, 12, 0, tzinfo=UTC)

        completed = season.with_detection_completed(attempted_at=ts)

        assert completed.intro_detection_attempted_at == ts


class TestWithDetectionFailed:
    """Tests for Season.with_detection_failed."""

    def test_should_capture_error_message(self):
        season = _make_season().with_detection_started()

        failed = season.with_detection_failed("ffmpeg returned non-zero")

        assert failed.intro_detection_state == IntroDetectionState.FAILED
        assert failed.intro_detection_error == "ffmpeg returned non-zero"
        assert failed.intro_detection_attempted_at is not None

    def test_should_truncate_oversized_error_messages(self):
        season = _make_season().with_detection_started()
        long_error = "x" * 5000

        failed = season.with_detection_failed(long_error)

        assert failed.intro_detection_state == IntroDetectionState.FAILED
        assert failed.intro_detection_error is not None
        assert len(failed.intro_detection_error) == Season._DETECTION_ERROR_MAX_LEN


class TestWithDetectionMarkedInsufficient:
    """Tests for Season.with_detection_marked_insufficient."""

    def test_should_transition_and_clear_error(self):
        season = _make_season().with_detection_failed("oops")

        result = season.with_detection_marked_insufficient()

        assert result.intro_detection_state == IntroDetectionState.INSUFFICIENT_EPISODES
        assert result.intro_detection_error is None
        assert result.intro_detection_attempted_at is not None


class TestWithDetectionDisabled:
    """Tests for Season.with_detection_disabled."""

    def test_should_transition_to_disabled_from_any_state(self):
        season = _make_season().with_detection_failed("some error")

        disabled = season.with_detection_disabled()

        assert disabled.intro_detection_state == IntroDetectionState.DISABLED
        assert disabled.intro_detection_error is None


class TestWithDetectionReset:
    """Tests for Season.with_detection_reset."""

    def test_should_clear_state_back_to_not_started(self):
        season = _make_season().with_detection_failed("boom")

        reset = season.with_detection_reset()

        assert reset.intro_detection_state == IntroDetectionState.NOT_STARTED
        assert reset.intro_detection_error is None
        assert reset.intro_detection_attempted_at is None

    def test_should_unblock_disabled_seasons(self):
        season = _make_season().with_detection_disabled()

        reset = season.with_detection_reset()
        started = reset.with_detection_started()

        assert started.intro_detection_state == IntroDetectionState.IN_PROGRESS
