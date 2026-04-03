"""Unit tests for MediaFileMapper."""

import json
from datetime import UTC, datetime

import pytest

from src.modules.media.domain.value_objects import (
    HdrFormat,
    MediaFile,
    Resolution,
    VideoCodec,
)
from src.modules.media.infrastructure.persistence.mappers import MediaFileMapper
from src.shared_kernel.value_objects.file_path import FilePath
from src.shared_kernel.value_objects.language_code import LanguageCode
from src.shared_kernel.value_objects.tracks import AudioTrack, SubtitleTrack


def _create_media_file(**overrides: object) -> MediaFile:
    """Create a MediaFile for testing."""
    defaults = {
        "file_path": FilePath("/movies/test.mkv"),
        "file_size": 4_000_000_000,
        "resolution": Resolution("1080p"),
        "is_primary": True,
        "added_at": datetime(2025, 1, 1, tzinfo=UTC),
    }
    defaults.update(overrides)
    return MediaFile(**defaults)


@pytest.mark.unit
class TestMediaFileMapperToModel:
    """Tests for MediaFileMapper.to_model()."""

    def test_maps_basic_fields(self) -> None:
        file = _create_media_file()
        model = MediaFileMapper.to_model(file)

        assert model.file_path == "/movies/test.mkv"
        assert model.file_size == 4_000_000_000
        assert model.resolution_name == "1080p"
        assert model.resolution_width == 1920
        assert model.resolution_height == 1080
        assert model.is_primary is True

    def test_maps_optional_fields(self) -> None:
        file = _create_media_file(
            video_codec=VideoCodec.H265,
            video_bitrate=8000,
            hdr_format=HdrFormat.HDR10,
        )
        model = MediaFileMapper.to_model(file)

        assert model.video_codec == "h265"
        assert model.video_bitrate == 8000
        assert model.hdr_format == "hdr10"

    def test_maps_none_optional_fields(self) -> None:
        file = _create_media_file()
        model = MediaFileMapper.to_model(file)

        assert model.video_codec is None
        assert model.video_bitrate is None
        assert model.hdr_format is None

    def test_serializes_audio_tracks_to_json(self) -> None:
        file = _create_media_file(
            audio_tracks=[
                AudioTrack(
                    index=0,
                    language=LanguageCode("en"),
                    codec="dts-hd",
                    channels=8,
                    is_default=True,
                ),
            ],
        )
        model = MediaFileMapper.to_model(file)

        assert model.audio_tracks_json is not None
        tracks = json.loads(model.audio_tracks_json)
        assert len(tracks) == 1
        assert tracks[0]["language"] == "en"
        assert tracks[0]["codec"] == "dts-hd"

    def test_serializes_subtitle_tracks_to_json(self) -> None:
        file = _create_media_file(
            subtitle_tracks=[
                SubtitleTrack(
                    index=0,
                    language=LanguageCode("pt"),
                    format="srt",
                    is_external=True,
                    file_path=FilePath("/movies/test.pt.srt"),
                ),
            ],
        )
        model = MediaFileMapper.to_model(file)

        assert model.subtitle_tracks_json is not None
        tracks = json.loads(model.subtitle_tracks_json)
        assert len(tracks) == 1
        assert tracks[0]["language"] == "pt"

    def test_no_tracks_produces_null_json(self) -> None:
        file = _create_media_file()
        model = MediaFileMapper.to_model(file)

        assert model.audio_tracks_json is None
        assert model.subtitle_tracks_json is None

    def test_does_not_set_owner_fks(self) -> None:
        file = _create_media_file()
        model = MediaFileMapper.to_model(file)

        assert model.movie_id is None
        assert model.episode_id is None


@pytest.mark.unit
class TestMediaFileMapperToEntity:
    """Tests for MediaFileMapper.to_entity()."""

    def test_round_trip_basic_fields(self) -> None:
        original = _create_media_file()
        model = MediaFileMapper.to_model(original)
        restored = MediaFileMapper.to_entity(model)

        assert restored.file_path == original.file_path
        assert restored.file_size == original.file_size
        assert restored.resolution == original.resolution
        assert restored.is_primary == original.is_primary

    def test_round_trip_optional_fields(self) -> None:
        original = _create_media_file(
            video_codec=VideoCodec.H265,
            video_bitrate=8000,
            hdr_format=HdrFormat.DOLBY_VISION,
        )
        model = MediaFileMapper.to_model(original)
        restored = MediaFileMapper.to_entity(model)

        assert restored.video_codec == VideoCodec.H265
        assert restored.video_bitrate == 8000
        assert restored.hdr_format == HdrFormat.DOLBY_VISION

    def test_round_trip_audio_tracks(self) -> None:
        original = _create_media_file(
            audio_tracks=[
                AudioTrack(
                    index=0,
                    language=LanguageCode("en"),
                    codec="aac",
                    channels=2,
                ),
                AudioTrack(
                    index=1,
                    language=LanguageCode("pt"),
                    codec="ac3",
                    channels=6,
                    is_default=True,
                ),
            ],
        )
        model = MediaFileMapper.to_model(original)
        restored = MediaFileMapper.to_entity(model)

        assert len(restored.audio_tracks) == 2
        assert restored.audio_tracks[0].language == LanguageCode("en")
        assert restored.audio_tracks[1].channels == 6

    def test_round_trip_subtitle_tracks(self) -> None:
        original = _create_media_file(
            subtitle_tracks=[
                SubtitleTrack(
                    index=0,
                    language=LanguageCode("en"),
                    format="pgs",
                    is_default=True,
                ),
            ],
        )
        model = MediaFileMapper.to_model(original)
        restored = MediaFileMapper.to_entity(model)

        assert len(restored.subtitle_tracks) == 1
        assert restored.subtitle_tracks[0].format == "pgs"


@pytest.mark.unit
class TestMediaFileMapperUpdateModel:
    """Tests for MediaFileMapper.update_model()."""

    def test_updates_all_fields(self) -> None:
        original = _create_media_file()
        model = MediaFileMapper.to_model(original)

        updated = _create_media_file(
            file_path=FilePath("/movies/updated.mkv"),
            file_size=8_000_000_000,
            resolution=Resolution("4K"),
            video_codec=VideoCodec.H265,
            is_primary=False,
        )

        MediaFileMapper.update_model(model, updated)

        assert model.file_path == "/movies/updated.mkv"
        assert model.file_size == 8_000_000_000
        assert model.resolution_name == "4K"
        assert model.video_codec == "h265"
        assert model.is_primary is False
