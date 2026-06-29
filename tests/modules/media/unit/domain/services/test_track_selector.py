"""Tests for the TrackSelector domain service (ADR-005)."""

import pytest

from src.modules.media.domain.services.track_selector import TrackSelector
from src.shared_kernel.value_objects.language_code import LanguageCode
from src.shared_kernel.value_objects.tracks import AudioTrack


def _audio(
    index: int,
    *,
    language: str = "en",
    channels: int = 2,
    is_default: bool = False,
) -> AudioTrack:
    return AudioTrack(
        index=index,
        language=LanguageCode(language),
        codec="aac",
        channels=channels,
        is_default=is_default,
    )


@pytest.mark.unit
class TestSelectAudio:
    def test_returns_none_for_no_tracks(self) -> None:
        assert TrackSelector().select_audio([]) is None

    def test_no_preference_falls_back_to_container_default(self) -> None:
        tracks = [_audio(0), _audio(1, is_default=True), _audio(2)]
        assert TrackSelector().select_audio(tracks) is tracks[1]

    def test_no_preference_no_default_falls_back_to_first(self) -> None:
        # Reproduces the old probe behaviour without persisting a fabricated flag.
        tracks = [_audio(0), _audio(1)]
        assert TrackSelector().select_audio(tracks) is tracks[0]

    def test_preferred_language_wins_over_container_default(self) -> None:
        tracks = [
            _audio(0, language="en", is_default=True),
            _audio(1, language="pt", channels=6),
        ]
        selected = TrackSelector().select_audio(tracks, LanguageCode("pt"))
        assert selected is tracks[1]

    def test_preferred_language_picks_most_channels(self) -> None:
        tracks = [
            _audio(0, language="pt", channels=2),
            _audio(1, language="pt", channels=8),
            _audio(2, language="en", channels=6),
        ]
        selected = TrackSelector().select_audio(tracks, LanguageCode("pt"))
        assert selected is tracks[1]

    def test_preferred_language_absent_falls_back_to_default_then_first(self) -> None:
        tracks = [_audio(0, language="en"), _audio(1, language="en", is_default=True)]
        # No Japanese track → fall through to the container default.
        assert TrackSelector().select_audio(tracks, LanguageCode("ja")) is tracks[1]

    def test_preferred_language_absent_no_default_falls_back_to_first(self) -> None:
        tracks = [_audio(0, language="en"), _audio(1, language="en")]
        assert TrackSelector().select_audio(tracks, LanguageCode("ja")) is tracks[0]
