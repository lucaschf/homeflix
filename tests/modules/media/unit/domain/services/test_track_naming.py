"""Tests for the track display-name domain service."""

import pytest

from src.shared_kernel.track_selection.track_naming import (
    TrackVersion,
    audio_version_labels,
    detect_studio,
    subtitle_version_labels,
)
from src.shared_kernel.value_objects.language_code import LanguageCode
from src.shared_kernel.value_objects.tracks import AudioTrack, SubtitleTrack


def _audio(index: int, lang: str, *, title: str | None = None, channels: int = 2) -> AudioTrack:
    return AudioTrack(
        index=index,
        language=LanguageCode(lang),
        codec="aac",
        channels=channels,
        title=title,
    )


def _sub(
    index: int,
    lang: str,
    *,
    title: str | None = None,
    forced: bool = False,
) -> SubtitleTrack:
    return SubtitleTrack(
        index=index,
        language=LanguageCode(lang),
        format="srt",
        title=title,
        is_forced=forced,
    )


@pytest.mark.unit
class TestDetectStudio:
    def test_should_detect_studio_inside_noisy_title(self) -> None:
        assert detect_studio("PT-BR Dublagem Herbert Richers AAC 5.1") == "Herbert Richers"

    def test_should_match_accent_insensitively(self) -> None:
        assert detect_studio("Áudio Dublavídeo") == "Dublavídeo"
        assert detect_studio("audio dublavideo") == "Dublavídeo"

    def test_should_match_streaming_studio_with_plus(self) -> None:
        assert detect_studio("Dublagem Disney+") == "Disney"

    def test_should_return_none_for_no_match(self) -> None:
        assert detect_studio("English DTS-HD MA 7.1") is None

    def test_should_return_none_for_missing_title(self) -> None:
        assert detect_studio(None) is None
        assert detect_studio("") is None

    def test_should_respect_token_boundaries(self) -> None:
        # "bks" must not match inside a larger word.
        assert detect_studio("playbkster") is None


@pytest.mark.unit
class TestAudioVersionLabels:
    def test_should_not_label_single_track_languages(self) -> None:
        tracks = [_audio(0, "en"), _audio(1, "pt")]

        labels = audio_version_labels(tracks)

        assert labels == {0: None, 1: None}

    def test_should_label_same_language_dubs_by_studio(self) -> None:
        tracks = [
            _audio(0, "pt", title="Dublagem Herbert Richers"),
            _audio(1, "pt", title="Redublagem Álamo"),
        ]

        labels = audio_version_labels(tracks)

        assert labels[0] == TrackVersion("studio", "Herbert Richers")
        assert labels[1] == TrackVersion("studio", "Álamo")

    def test_should_fall_back_to_channel_layout(self) -> None:
        tracks = [
            _audio(0, "pt", title="AAC", channels=6),
            _audio(1, "pt", title="AAC", channels=2),
        ]

        labels = audio_version_labels(tracks)

        assert labels[0] == TrackVersion("channel_layout", "5.1")
        assert labels[1] == TrackVersion("channel_layout", "Stereo")

    def test_should_fall_back_to_ordinal_when_indistinguishable(self) -> None:
        tracks = [
            _audio(0, "pt", title="AAC", channels=2),
            _audio(1, "pt", title="Stereo", channels=2),
        ]

        labels = audio_version_labels(tracks)

        assert labels[0] == TrackVersion("ordinal", "1")
        assert labels[1] == TrackVersion("ordinal", "2")

    def test_should_mix_studio_and_layout_within_a_group(self) -> None:
        tracks = [
            _audio(0, "pt", title="Herbert Richers", channels=6),
            _audio(1, "pt", title="AAC", channels=2),
        ]

        labels = audio_version_labels(tracks)

        assert labels[0] == TrackVersion("studio", "Herbert Richers")
        assert labels[1] == TrackVersion("channel_layout", "Stereo")

    def test_should_number_repeated_studio_names(self) -> None:
        tracks = [
            _audio(0, "pt", title="Netflix", channels=2),
            _audio(1, "pt", title="Netflix", channels=2),
        ]

        labels = audio_version_labels(tracks)

        assert labels[0] == TrackVersion("studio", "Netflix 1")
        assert labels[1] == TrackVersion("studio", "Netflix 2")

    def test_should_keep_distinct_studios_while_numbering_repeats(self) -> None:
        # Real-world case: 3 Herbert Richers takes + DublaVídeo + Centauro,
        # all pt-BR. Repeats are numbered; the other studios keep their name
        # (previously the whole group collapsed to plain ordinals).
        tracks = [
            _audio(0, "pt", title="1ª Dublagem Clássica - Herbert Richers - Completa"),
            _audio(1, "pt", title="2ª Dublagem Clássica - Herbert Richers - Fonte 2 - 2.0"),
            _audio(2, "pt", title="2ª Dublagem Clássica - Herbert Richers - 2.0"),
            _audio(3, "pt", title="3ª Redublagem - DublaVideo SP"),
            _audio(4, "pt", title="4ª Redublagem - Centauro"),
            _audio(5, "en", title="Inglês - 5.1", channels=6),
        ]

        labels = audio_version_labels(tracks)

        assert labels[0] == TrackVersion("studio", "Herbert Richers 1")
        assert labels[1] == TrackVersion("studio", "Herbert Richers 2")
        assert labels[2] == TrackVersion("studio", "Herbert Richers 3")
        assert labels[3] == TrackVersion("studio", "Dublavídeo")
        assert labels[4] == TrackVersion("studio", "Centauro")
        assert labels[5] is None  # single English track → just the language

    def test_should_label_each_language_group_independently(self) -> None:
        tracks = [
            _audio(0, "en"),
            _audio(1, "pt", title="Herbert Richers"),
            _audio(2, "pt", title="Álamo"),
        ]

        labels = audio_version_labels(tracks)

        assert labels[0] is None
        assert labels[1] == TrackVersion("studio", "Herbert Richers")
        assert labels[2] == TrackVersion("studio", "Álamo")


@pytest.mark.unit
class TestSubtitleVersionLabels:
    def test_should_not_label_single_track_languages(self) -> None:
        labels = subtitle_version_labels([_sub(0, "en"), _sub(1, "pt")])

        assert labels == {0: None, 1: None}

    def test_should_not_label_forced_vs_full_same_language(self) -> None:
        # Forced is surfaced separately, so neither needs a version label.
        labels = subtitle_version_labels(
            [_sub(0, "pt"), _sub(1, "pt", forced=True)],
        )

        assert labels == {0: None, 1: None}

    def test_should_label_sdh_subtitles(self) -> None:
        labels = subtitle_version_labels(
            [_sub(0, "pt"), _sub(1, "pt", title="Português SDH")],
        )

        assert labels[0] is None
        assert labels[1] == TrackVersion("sdh")

    def test_should_ordinal_genuine_duplicates(self) -> None:
        labels = subtitle_version_labels(
            [_sub(0, "pt", title="Full"), _sub(1, "pt", title="Completa")],
        )

        assert labels[0] == TrackVersion("ordinal", "1")
        assert labels[1] == TrackVersion("ordinal", "2")
