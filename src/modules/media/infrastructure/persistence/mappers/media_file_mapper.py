"""Mapper between MediaFile domain value object and MediaFileModel."""

import json
import secrets
import string

from src.modules.media.domain.value_objects import (
    HdrFormat,
    MediaFile,
    Resolution,
    VideoCodec,
)
from src.modules.media.infrastructure.persistence.models import MediaFileModel
from src.shared_kernel.value_objects.file_path import FilePath
from src.shared_kernel.value_objects.tracks import AudioTrack, SubtitleTrack


class MediaFileMapper:
    """Bidirectional mapper between MediaFile value object and MediaFileModel.

    Handles serialization of audio/subtitle tracks to JSON for storage
    and reconstruction of the full MediaFile from database records.

    Example:
        >>> model = MediaFileMapper.to_model(media_file)
        >>> entity = MediaFileMapper.to_entity(model)
    """

    @staticmethod
    def to_model(file: MediaFile) -> MediaFileModel:
        """Convert MediaFile value object to MediaFileModel.

        Does not set movie_id or episode_id — those are assigned
        by the ORM when the model is appended to a relationship list.

        Args:
            file: The domain MediaFile value object.

        Returns:
            MediaFileModel ready for persistence.
        """
        audio_json = None
        if file.audio_tracks:
            audio_json = json.dumps(
                [track.model_dump(mode="json") for track in file.audio_tracks],
            )

        subtitle_json = None
        if file.subtitle_tracks:
            subtitle_json = json.dumps(
                [track.model_dump(mode="json") for track in file.subtitle_tracks],
            )

        return MediaFileModel(
            external_id=_generate_mfl_id(),
            file_path=file.file_path.value,
            file_size=file.file_size,
            resolution_width=file.resolution.width,
            resolution_height=file.resolution.height,
            resolution_name=file.resolution.name,
            video_codec=file.video_codec.value if file.video_codec else None,
            video_bitrate=file.video_bitrate,
            hdr_format=file.hdr_format.value if file.hdr_format else None,
            is_primary=file.is_primary,
            added_at=file.added_at,
            audio_tracks_json=audio_json,
            subtitle_tracks_json=subtitle_json,
        )

    @staticmethod
    def to_entity(model: MediaFileModel) -> MediaFile:
        """Convert MediaFileModel to MediaFile value object.

        Args:
            model: The SQLAlchemy MediaFileModel.

        Returns:
            Domain MediaFile with reconstructed value objects.
        """
        audio_tracks: list[AudioTrack] = []
        if model.audio_tracks_json:
            audio_tracks = [AudioTrack(**data) for data in json.loads(model.audio_tracks_json)]

        subtitle_tracks: list[SubtitleTrack] = []
        if model.subtitle_tracks_json:
            subtitle_tracks = [
                SubtitleTrack(**data) for data in json.loads(model.subtitle_tracks_json)
            ]

        return MediaFile(
            file_path=FilePath(model.file_path),
            file_size=model.file_size,
            resolution=Resolution(model.resolution_name),
            video_codec=VideoCodec(model.video_codec) if model.video_codec else None,
            video_bitrate=model.video_bitrate,
            hdr_format=HdrFormat(model.hdr_format) if model.hdr_format else None,
            is_primary=model.is_primary,
            added_at=model.added_at,
            audio_tracks=audio_tracks,
            subtitle_tracks=subtitle_tracks,
        )

    @staticmethod
    def update_model(model: MediaFileModel, file: MediaFile) -> MediaFileModel:
        """Update existing MediaFileModel with value object data.

        Args:
            model: The existing SQLAlchemy MediaFileModel.
            file: The domain MediaFile with updated data.

        Returns:
            The updated MediaFileModel.
        """
        model.file_path = file.file_path.value
        model.file_size = file.file_size
        model.resolution_width = file.resolution.width
        model.resolution_height = file.resolution.height
        model.resolution_name = file.resolution.name
        model.video_codec = file.video_codec.value if file.video_codec else None
        model.video_bitrate = file.video_bitrate
        model.hdr_format = file.hdr_format.value if file.hdr_format else None
        model.is_primary = file.is_primary
        model.added_at = file.added_at

        if file.audio_tracks:
            model.audio_tracks_json = json.dumps(
                [track.model_dump(mode="json") for track in file.audio_tracks],
            )
        else:
            model.audio_tracks_json = None

        if file.subtitle_tracks:
            model.subtitle_tracks_json = json.dumps(
                [track.model_dump(mode="json") for track in file.subtitle_tracks],
            )
        else:
            model.subtitle_tracks_json = None

        return model


_ALPHABET = string.ascii_letters + string.digits


def _generate_mfl_id() -> str:
    """Generate a unique external ID for a media file record."""
    random_part = "".join(secrets.choice(_ALPHABET) for _ in range(12))
    return f"mfl_{random_part}"


__all__ = ["MediaFileMapper"]
