"""Tests for AudioTrack and SubtitleTrack value objects."""

import pytest

from src.domain.library.value_objects.language_code import LanguageCode
from src.domain.library.value_objects.tracks import AudioTrack, SubtitleTrack
from src.domain.media.value_objects.file_path import FilePath
from src.domain.shared.exceptions.domain import DomainValidationException


class TestAudioTrackCreation:
    """Tests for AudioTrack instantiation."""

    def test_should_create_with_required_fields(self):
        track = AudioTrack(
            index=0,
            language=LanguageCode("en"),
            codec="aac",
            channels=2,
        )

        assert track.index == 0
        assert track.language.value == "en"
        assert track.codec == "aac"
        assert track.channels == 2

    def test_should_create_with_all_fields(self):
        track = AudioTrack(
            index=1,
            language=LanguageCode("en"),
            codec="dts-hd",
            channels=8,
            title="English DTS-HD MA 7.1",
            is_default=True,
            bitrate=5000,
        )

        assert track.title == "English DTS-HD MA 7.1"
        assert track.is_default is True
        assert track.bitrate == 5000

    def test_should_default_optional_fields(self):
        track = AudioTrack(
            index=0,
            language=LanguageCode("en"),
            codec="aac",
            channels=2,
        )

        assert track.title is None
        assert track.is_default is False
        assert track.bitrate is None


class TestAudioTrackValidation:
    """Tests for AudioTrack validation."""

    def test_should_raise_error_for_negative_index(self):
        with pytest.raises(DomainValidationException):
            AudioTrack(
                index=-1,
                language=LanguageCode("en"),
                codec="aac",
                channels=2,
            )

    def test_should_raise_error_for_zero_channels(self):
        with pytest.raises(DomainValidationException):
            AudioTrack(
                index=0,
                language=LanguageCode("en"),
                codec="aac",
                channels=0,
            )

    def test_should_raise_error_for_channels_above_16(self):
        with pytest.raises(DomainValidationException):
            AudioTrack(
                index=0,
                language=LanguageCode("en"),
                codec="aac",
                channels=17,
            )

    def test_should_raise_error_for_negative_bitrate(self):
        with pytest.raises(DomainValidationException):
            AudioTrack(
                index=0,
                language=LanguageCode("en"),
                codec="aac",
                channels=2,
                bitrate=-1,
            )


class TestAudioTrackProperties:
    """Tests for AudioTrack properties."""

    def test_is_stereo_should_return_true_for_2_channels(self):
        track = AudioTrack(
            index=0,
            language=LanguageCode("en"),
            codec="aac",
            channels=2,
        )

        assert track.is_stereo is True
        assert track.is_surround is False

    def test_is_surround_should_return_true_for_more_than_2_channels(self):
        track = AudioTrack(
            index=0,
            language=LanguageCode("en"),
            codec="dts",
            channels=6,
        )

        assert track.is_surround is True
        assert track.is_stereo is False

    def test_channel_layout_should_return_correct_labels(self):
        mono = AudioTrack(index=0, language=LanguageCode("en"), codec="aac", channels=1)
        stereo = AudioTrack(index=0, language=LanguageCode("en"), codec="aac", channels=2)
        surround_51 = AudioTrack(index=0, language=LanguageCode("en"), codec="dts", channels=6)
        surround_71 = AudioTrack(index=0, language=LanguageCode("en"), codec="dts", channels=8)
        custom = AudioTrack(index=0, language=LanguageCode("en"), codec="aac", channels=4)

        assert mono.channel_layout == "Mono"
        assert stereo.channel_layout == "Stereo"
        assert surround_51.channel_layout == "5.1"
        assert surround_71.channel_layout == "7.1"
        assert custom.channel_layout == "4ch"


class TestSubtitleTrackCreation:
    """Tests for SubtitleTrack instantiation."""

    def test_should_create_embedded_track(self):
        track = SubtitleTrack(
            index=0,
            language=LanguageCode("en"),
            format="pgs",
            is_external=False,
        )

        assert track.index == 0
        assert track.language.value == "en"
        assert track.format == "pgs"
        assert track.is_external is False
        assert track.file_path is None

    def test_should_create_external_track_with_file_path(self):
        track = SubtitleTrack(
            index=2,
            language=LanguageCode("pt"),
            format="srt",
            is_external=True,
            file_path=FilePath("/movies/Movie.pt-BR.srt"),
        )

        assert track.is_external is True
        assert track.file_path is not None
        assert track.file_path.value == "/movies/Movie.pt-BR.srt"

    def test_should_create_forced_track(self):
        track = SubtitleTrack(
            index=0,
            language=LanguageCode("en"),
            format="pgs",
            is_forced=True,
        )

        assert track.is_forced is True


class TestSubtitleTrackValidation:
    """Tests for SubtitleTrack validation."""

    def test_should_raise_error_for_negative_index(self):
        with pytest.raises(DomainValidationException):
            SubtitleTrack(
                index=-1,
                language=LanguageCode("en"),
                format="srt",
            )

    def test_should_raise_error_for_external_without_file_path(self):
        with pytest.raises(DomainValidationException, match="file_path"):
            SubtitleTrack(
                index=0,
                language=LanguageCode("en"),
                format="srt",
                is_external=True,
                file_path=None,
            )


class TestSubtitleTrackProperties:
    """Tests for SubtitleTrack properties."""

    def test_is_text_based_should_return_true_for_text_formats(self):
        text_formats = ["srt", "ass", "ssa", "vtt", "sub"]

        for fmt in text_formats:
            track = SubtitleTrack(
                index=0,
                language=LanguageCode("en"),
                format=fmt,
            )
            assert track.is_text_based is True, f"Expected {fmt} to be text-based"
            assert track.is_image_based is False

    def test_is_image_based_should_return_true_for_image_formats(self):
        image_formats = ["pgs", "sup", "vobsub"]

        for fmt in image_formats:
            track = SubtitleTrack(
                index=0,
                language=LanguageCode("en"),
                format=fmt,
            )
            assert track.is_image_based is True, f"Expected {fmt} to be image-based"
            assert track.is_text_based is False
