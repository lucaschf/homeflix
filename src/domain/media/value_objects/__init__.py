"""Media domain value objects."""

from src.domain.media.value_objects.duration import Duration
from src.domain.media.value_objects.file_path import FilePath
from src.domain.media.value_objects.genre import Genre
from src.domain.media.value_objects.hdr_format import HdrFormat
from src.domain.media.value_objects.media_file import MediaFile
from src.domain.media.value_objects.media_id import (
    EpisodeId,
    MediaId,
    MovieId,
    SeasonId,
    SeriesId,
    parse_media_id,
)
from src.domain.media.value_objects.resolution import Resolution
from src.domain.media.value_objects.title import Title
from src.domain.media.value_objects.tracks import AudioTrack, SubtitleTrack
from src.domain.media.value_objects.video_codec import VideoCodec
from src.domain.media.value_objects.year import Year

__all__ = [
    "AudioTrack",
    "Duration",
    "EpisodeId",
    "FilePath",
    "Genre",
    "HdrFormat",
    "MediaFile",
    "MediaId",
    "MovieId",
    "Resolution",
    "SeasonId",
    "SeriesId",
    "SubtitleTrack",
    "Title",
    "VideoCodec",
    "Year",
    "parse_media_id",
]
