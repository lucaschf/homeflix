"""Tests for Episode intro-marker behavior."""

from datetime import UTC, datetime

import pytest

from src.building_blocks.domain.errors import (
    BusinessRuleViolationException,
    DomainValidationException,
)
from src.modules.media.domain.entities import Episode
from src.modules.media.domain.rule_codes import MediaRuleCodes
from src.modules.media.domain.value_objects import (
    Duration,
    FilePath,
    IntroMarker,
    IntroMarkerSource,
    IntroStatus,
    MediaFile,
    Resolution,
    SeriesId,
    Title,
)


def _make_episode(duration_seconds: int = 2700) -> Episode:
    return Episode(
        series_id=SeriesId.generate(),
        season_number=1,
        episode_number=1,
        title=Title("Pilot"),
        duration=Duration(duration_seconds),
        files=[
            MediaFile(
                file_path=FilePath("/series/show/s01e01.mkv"),
                file_size=1_000_000_000,
                resolution=Resolution("1080p"),
                is_primary=True,
            )
        ],
    )


class TestEpisodeWithIntroMarker:
    """Tests for Episode.with_intro_marker."""

    def test_should_attach_marker_to_episode(self):
        episode = _make_episode()
        marker = IntroMarker(
            start_seconds=10,
            end_seconds=80,
            source=IntroMarkerSource.MANUAL,
        )

        updated = episode.with_intro_marker(marker)

        assert updated.intro == marker
        assert episode.intro is None  # original untouched

    def test_should_return_self_when_marker_is_unchanged(self):
        episode = _make_episode()
        marker = IntroMarker(
            start_seconds=10,
            end_seconds=80,
            source=IntroMarkerSource.MANUAL,
        )
        first = episode.with_intro_marker(marker)

        second = first.with_intro_marker(marker)

        assert second is first

    def test_should_replace_existing_marker(self):
        episode = _make_episode()
        first = IntroMarker(
            start_seconds=10,
            end_seconds=80,
            source=IntroMarkerSource.MANUAL,
        )
        second = IntroMarker(
            start_seconds=15,
            end_seconds=90,
            source=IntroMarkerSource.AUTO_DETECTED,
            confidence=0.88,
        )

        updated = episode.with_intro_marker(first).with_intro_marker(second)

        assert updated.intro == second

    def test_should_raise_when_end_exceeds_duration(self):
        episode = _make_episode(duration_seconds=120)
        marker = IntroMarker(
            start_seconds=10,
            end_seconds=130,
            source=IntroMarkerSource.MANUAL,
        )

        with pytest.raises(BusinessRuleViolationException) as exc_info:
            episode.with_intro_marker(marker)

        assert exc_info.value.rule_code == MediaRuleCodes.INTRO_EXCEEDS_DURATION

    def test_should_allow_end_equal_to_duration(self):
        episode = _make_episode(duration_seconds=120)
        marker = IntroMarker(
            start_seconds=10,
            end_seconds=120,
            source=IntroMarkerSource.MANUAL,
        )

        updated = episode.with_intro_marker(marker)

        assert updated.intro is not None
        assert updated.intro.end_seconds == 120


class TestEpisodeWithIntroCleared:
    """Tests for Episode.with_intro_cleared."""

    def test_should_remove_existing_marker(self):
        episode = _make_episode().with_intro_marker(
            IntroMarker(
                start_seconds=10,
                end_seconds=60,
                source=IntroMarkerSource.MANUAL,
            )
        )

        cleared = episode.with_intro_cleared()

        assert cleared.intro is None

    def test_should_return_self_when_already_clear(self):
        episode = _make_episode()

        result = episode.with_intro_cleared()

        assert result is episode

    def test_should_bump_updated_at_when_clearing_existing_marker(self):
        episode = _make_episode().with_intro_marker(
            IntroMarker(
                start_seconds=10,
                end_seconds=60,
                source=IntroMarkerSource.MANUAL,
            )
        )

        cleared = episode.with_intro_cleared()

        assert cleared.updated_at >= episode.updated_at


class TestEpisodeIntroAbsent:
    """Tests for the third intro state: confirmed to have no intro."""

    def test_starts_pending(self) -> None:
        episode = _make_episode()

        assert episode.intro_status is IntroStatus.PENDING
        assert episode.intro_resolved is False

    def test_marking_absent_sets_the_absent_status(self) -> None:
        episode = _make_episode().with_intro_marked_absent()

        assert episode.intro_status is IntroStatus.ABSENT
        assert episode.intro_resolved is True
        assert episode.intro_absent_at is not None

    def test_marking_absent_drops_an_existing_marker(self) -> None:
        """The two states are exclusive, so the marker must go."""
        marker = IntroMarker(start_seconds=10, end_seconds=80, source=IntroMarkerSource.MANUAL)
        episode = _make_episode().with_intro_marker(marker)

        absent = episode.with_intro_marked_absent()

        assert absent.intro is None
        assert absent.intro_status is IntroStatus.ABSENT

    def test_setting_a_marker_clears_the_absent_flag(self) -> None:
        """Recording a span contradicts the verdict, so it is dropped."""
        episode = _make_episode().with_intro_marked_absent()
        marker = IntroMarker(start_seconds=10, end_seconds=80, source=IntroMarkerSource.MANUAL)

        marked = episode.with_intro_marker(marker)

        assert marked.intro_absent_at is None
        assert marked.intro_status is IntroStatus.MARKED

    def test_clearing_reopens_an_absent_verdict(self) -> None:
        episode = _make_episode().with_intro_marked_absent()

        cleared = episode.with_intro_cleared()

        assert cleared.intro_absent_at is None
        assert cleared.intro_status is IntroStatus.PENDING

    def test_marking_absent_twice_returns_self(self) -> None:
        episode = _make_episode().with_intro_marked_absent()

        assert episode.with_intro_marked_absent() is episode

    def test_clearing_a_pending_episode_returns_self(self) -> None:
        episode = _make_episode()

        assert episode.with_intro_cleared() is episode

    def test_accepts_an_explicit_marked_at(self) -> None:
        stamp = datetime(2026, 8, 29, 12, 0, tzinfo=UTC)

        episode = _make_episode().with_intro_marked_absent(stamp)

        assert episode.intro_absent_at == stamp

    def test_rejects_an_episode_that_is_both_marked_and_absent(self) -> None:
        """Guards entities built directly, bypassing the mutators."""
        marker = IntroMarker(start_seconds=10, end_seconds=80, source=IntroMarkerSource.MANUAL)

        with pytest.raises(DomainValidationException, match="cannot both be set"):
            Episode(
                series_id=SeriesId.generate(),
                season_number=1,
                episode_number=1,
                title=Title("Pilot"),
                duration=Duration(2700),
                intro=marker,
                intro_absent_at=datetime(2026, 8, 29, tzinfo=UTC),
            )
