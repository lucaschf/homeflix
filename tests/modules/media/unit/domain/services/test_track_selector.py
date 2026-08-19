"""Tests for the TrackSelector domain service (ADR-005 / ADR-026)."""

import pytest

from src.shared_kernel.track_selection.track_selector import TrackSelector
from src.shared_kernel.value_objects.language_code import LanguageCode
from src.shared_kernel.value_objects.subtitle_mode import SubtitleMode
from src.shared_kernel.value_objects.tracks import AudioTrack, SubtitleTrack


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


def _sub(
    index: int,
    *,
    language: str = "en",
    is_forced: bool = False,
) -> SubtitleTrack:
    return SubtitleTrack(
        index=index,
        language=LanguageCode(language),
        format="srt",
        is_forced=is_forced,
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


@pytest.mark.unit
class TestSelectSubtitle:
    _PT = LanguageCode("pt")
    _EN = LanguageCode("en")

    def test_returns_none_for_no_subtitles(self) -> None:
        assert TrackSelector().select_subtitle([], self._EN, self._PT, SubtitleMode.ALWAYS) is None

    def test_off_never_selects(self) -> None:
        subs = [_sub(0, language="pt")]
        assert TrackSelector().select_subtitle(subs, self._EN, self._PT, SubtitleMode.OFF) is None

    def test_forced_only_returns_first_forced_regardless_of_language(self) -> None:
        subs = [_sub(0, language="pt"), _sub(1, language="de", is_forced=True)]
        selected = TrackSelector().select_subtitle(
            subs, self._EN, self._PT, SubtitleMode.FORCED_ONLY
        )
        assert selected is subs[1]

    def test_forced_only_none_when_no_forced_track(self) -> None:
        subs = [_sub(0, language="pt"), _sub(1, language="de")]
        assert (
            TrackSelector().select_subtitle(subs, self._EN, self._PT, SubtitleMode.FORCED_ONLY)
            is None
        )

    def test_always_returns_preferred_language(self) -> None:
        subs = [_sub(0, language="de"), _sub(1, language="pt")]
        selected = TrackSelector().select_subtitle(subs, self._EN, self._PT, SubtitleMode.ALWAYS)
        assert selected is subs[1]

    def test_always_none_when_preferred_language_absent(self) -> None:
        subs = [_sub(0, language="de")]
        assert (
            TrackSelector().select_subtitle(subs, self._EN, self._PT, SubtitleMode.ALWAYS) is None
        )

    def test_always_none_when_no_preferred_language(self) -> None:
        subs = [_sub(0, language="pt")]
        assert TrackSelector().select_subtitle(subs, self._EN, None, SubtitleMode.ALWAYS) is None

    def test_foreign_only_shows_sub_when_audio_is_foreign(self) -> None:
        # Audio en, viewer prefers pt subs → foreign audio → show pt sub.
        subs = [_sub(0, language="pt")]
        selected = TrackSelector().select_subtitle(
            subs, self._EN, self._PT, SubtitleMode.FOREIGN_ONLY
        )
        assert selected is subs[0]

    def test_foreign_only_hides_sub_when_audio_matches_preferred(self) -> None:
        # Audio pt, viewer prefers pt subs → not foreign → no sub.
        subs = [_sub(0, language="pt")]
        assert (
            TrackSelector().select_subtitle(subs, self._PT, self._PT, SubtitleMode.FOREIGN_ONLY)
            is None
        )

    def test_foreign_only_none_when_preferred_language_absent(self) -> None:
        # Foreign audio, but no subtitle in the preferred language → None.
        subs = [_sub(0, language="de")]
        assert (
            TrackSelector().select_subtitle(subs, self._EN, self._PT, SubtitleMode.FOREIGN_ONLY)
            is None
        )
