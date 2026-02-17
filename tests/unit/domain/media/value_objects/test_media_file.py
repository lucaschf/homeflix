"""Tests for MediaFile value object."""

import pytest

from src.domain.media.value_objects import (
    AudioTrack,
    FilePath,
    HdrFormat,
    MediaFile,
    Resolution,
    SubtitleTrack,
    VideoCodec,
)
from src.domain.shared.exceptions.domain import DomainValidationException
from src.domain.shared.value_objects.language_code import LanguageCode


class TestMediaFileCreation:
    """Tests for MediaFile instantiation."""

    def test_should_create_with_required_fields(self):
        media_file = MediaFile(
            file_path=FilePath("/movies/inception.mkv"),
            file_size=4_000_000_000,
            resolution=Resolution("1080p"),
        )

        assert media_file.file_path.value == "/movies/inception.mkv"
        assert media_file.file_size == 4_000_000_000
        assert media_file.resolution.name == "1080p"
        assert media_file.video_codec is None
        assert media_file.video_bitrate is None
        assert media_file.hdr_format is None
        assert media_file.audio_tracks == []
        assert media_file.subtitle_tracks == []
        assert media_file.is_primary is False

    def test_should_create_with_all_fields(self):
        audio = AudioTrack(
            index=0,
            language=LanguageCode("en"),
            codec="dts-hd",
            channels=8,
        )
        subtitle = SubtitleTrack(
            index=0,
            language=LanguageCode("en"),
            format="srt",
        )

        media_file = MediaFile(
            file_path=FilePath("/movies/inception_4k.mkv"),
            file_size=20_000_000_000,
            resolution=Resolution("4K"),
            video_codec=VideoCodec.H265,
            video_bitrate=50000,
            hdr_format=HdrFormat.HDR10,
            audio_tracks=[audio],
            subtitle_tracks=[subtitle],
            is_primary=True,
        )

        assert media_file.video_codec == VideoCodec.H265
        assert media_file.video_bitrate == 50000
        assert media_file.hdr_format == HdrFormat.HDR10
        assert len(media_file.audio_tracks) == 1
        assert len(media_file.subtitle_tracks) == 1
        assert media_file.is_primary is True

    def test_should_have_added_at_timestamp(self):
        media_file = MediaFile(
            file_path=FilePath("/movies/test.mkv"),
            file_size=1_000_000_000,
            resolution=Resolution("1080p"),
        )

        assert media_file.added_at is not None


class TestMediaFileValidation:
    """Tests for MediaFile field validation."""

    def test_should_raise_for_negative_file_size(self):
        with pytest.raises(DomainValidationException):
            MediaFile(
                file_path=FilePath("/movies/test.mkv"),
                file_size=-1,
                resolution=Resolution("1080p"),
            )

    def test_should_raise_for_negative_bitrate(self):
        with pytest.raises(DomainValidationException):
            MediaFile(
                file_path=FilePath("/movies/test.mkv"),
                file_size=1_000_000_000,
                resolution=Resolution("1080p"),
                video_bitrate=-100,
            )

    def test_should_allow_zero_file_size(self):
        media_file = MediaFile(
            file_path=FilePath("/movies/test.mkv"),
            file_size=0,
            resolution=Resolution("1080p"),
        )

        assert media_file.file_size == 0


class TestMediaFileImmutability:
    """Tests for MediaFile immutability."""

    def test_should_be_immutable(self):
        media_file = MediaFile(
            file_path=FilePath("/movies/test.mkv"),
            file_size=1_000_000_000,
            resolution=Resolution("1080p"),
        )

        with pytest.raises(DomainValidationException):
            media_file.is_primary = True  # type: ignore[misc]


class TestMediaFileEquality:
    """Tests for MediaFile equality."""

    def test_should_be_equal_with_same_values(self):
        from datetime import UTC, datetime

        fixed_time = datetime(2024, 1, 1, tzinfo=UTC)
        kwargs = {
            "file_path": FilePath("/movies/test.mkv"),
            "file_size": 1_000_000_000,
            "resolution": Resolution("1080p"),
            "is_primary": True,
            "added_at": fixed_time,
        }

        mf1 = MediaFile(**kwargs)
        mf2 = MediaFile(**kwargs)

        assert mf1 == mf2

    def test_should_not_be_equal_with_different_path(self):
        mf1 = MediaFile(
            file_path=FilePath("/movies/test1.mkv"),
            file_size=1_000_000_000,
            resolution=Resolution("1080p"),
        )
        mf2 = MediaFile(
            file_path=FilePath("/movies/test2.mkv"),
            file_size=1_000_000_000,
            resolution=Resolution("1080p"),
        )

        assert mf1 != mf2
