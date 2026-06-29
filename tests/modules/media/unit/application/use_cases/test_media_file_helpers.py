"""Tests for to_media_file_output track mapping."""

import pytest

from src.modules.media.application.use_cases._media_file_helpers import to_media_file_output
from src.modules.media.domain.value_objects import MediaFile, Resolution
from src.shared_kernel.value_objects.file_path import FilePath
from src.shared_kernel.value_objects.language_code import LanguageCode
from src.shared_kernel.value_objects.tracks import AudioTrack, SubtitleTrack


def _media_file_with_tracks() -> MediaFile:
    return MediaFile(
        file_path=FilePath("/movies/movie.mkv"),
        file_size=4_000_000_000,
        resolution=Resolution("1080p"),
        is_primary=True,
        audio_tracks=[
            AudioTrack(
                index=0,
                language=LanguageCode("en"),
                codec="dts",
                channels=6,
                title="English DTS 5.1",
                is_default=True,
            ),
            AudioTrack(
                index=1,
                language=LanguageCode("ja"),
                codec="aac",
                channels=2,
                is_default=False,
            ),
        ],
        subtitle_tracks=[
            SubtitleTrack(
                index=0,
                language=LanguageCode("en"),
                format="srt",
                is_default=True,
                is_forced=False,
                is_external=False,
            ),
            SubtitleTrack(
                index=1,
                language=LanguageCode("pt"),
                format="srt",
                title="External (SRT)",
                is_default=False,
                is_forced=False,
                is_external=True,
                file_path=FilePath("/movies/movie.pt.srt"),
            ),
        ],
    )


@pytest.mark.unit
class TestToMediaFileOutputTracks:
    """Tests for audio/subtitle track mapping in to_media_file_output."""

    def test_should_preserve_audio_track_count(self) -> None:
        output = to_media_file_output(_media_file_with_tracks())
        assert len(output.audio_tracks) == 2

    def test_should_preserve_subtitle_track_count(self) -> None:
        output = to_media_file_output(_media_file_with_tracks())
        assert len(output.subtitle_tracks) == 2

    def test_should_map_audio_track_fields(self) -> None:
        output = to_media_file_output(_media_file_with_tracks())
        a0 = output.audio_tracks[0]

        assert a0.index == 0
        assert a0.language == "en"
        assert a0.codec == "dts"
        assert a0.channels == 6
        assert a0.channel_layout == "5.1"
        assert a0.title == "English DTS 5.1"
        assert a0.is_default is True

    def test_should_map_secondary_audio_track(self) -> None:
        output = to_media_file_output(_media_file_with_tracks())
        a1 = output.audio_tracks[1]

        assert a1.index == 1
        assert a1.language == "ja"
        assert a1.codec == "aac"
        assert a1.channels == 2
        assert a1.channel_layout == "Stereo"
        assert a1.title is None
        assert a1.is_default is False

    def test_should_map_embedded_subtitle_fields(self) -> None:
        output = to_media_file_output(_media_file_with_tracks())
        s0 = output.subtitle_tracks[0]

        assert s0.index == 0
        assert s0.language == "en"
        assert s0.format == "srt"
        assert s0.is_default is True
        assert s0.is_forced is False
        assert s0.is_external is False

    def test_should_map_external_subtitle_fields(self) -> None:
        output = to_media_file_output(_media_file_with_tracks())
        s1 = output.subtitle_tracks[1]

        assert s1.index == 1
        assert s1.language == "pt"
        assert s1.format == "srt"
        assert s1.title == "External (SRT)"
        assert s1.is_default is False
        assert s1.is_forced is False
        assert s1.is_external is True

    def test_marks_first_audio_default_when_container_declares_none(self) -> None:
        # New scans persist truthful is_default (possibly all-False); the
        # output still reports exactly one default audio via the selector.
        media_file = MediaFile(
            file_path=FilePath("/movies/movie.mkv"),
            file_size=1_000,
            resolution=Resolution("1080p"),
            is_primary=True,
            audio_tracks=[
                AudioTrack(index=0, language=LanguageCode("en"), codec="aac", channels=2),
                AudioTrack(index=1, language=LanguageCode("pt"), codec="ac3", channels=6),
            ],
        )
        output = to_media_file_output(media_file)

        defaults = [a for a in output.audio_tracks if a.is_default]
        assert len(defaults) == 1
        assert defaults[0].index == 0

    def test_should_return_empty_tracks_when_none_present(self) -> None:
        media_file = MediaFile(
            file_path=FilePath("/movies/movie.mkv"),
            file_size=1_000,
            resolution=Resolution("720p"),
            is_primary=True,
        )
        output = to_media_file_output(media_file)

        assert output.audio_tracks == []
        assert output.subtitle_tracks == []
