"""Tests for Episode intro-marker behavior."""

import pytest

from src.building_blocks.domain.errors import BusinessRuleViolationException
from src.modules.media.domain.entities import Episode
from src.modules.media.domain.rule_codes import MediaRuleCodes
from src.modules.media.domain.value_objects import (
    Duration,
    FilePath,
    IntroMarker,
    IntroMarkerSource,
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
