"""Media domain value objects."""

from src.modules.media.domain.value_objects.air_date import AirDate
from src.modules.media.domain.value_objects.duration import Duration
from src.modules.media.domain.value_objects.genre import Genre
from src.modules.media.domain.value_objects.hdr_format import HdrFormat
from src.modules.media.domain.value_objects.media_file import MediaFile
from src.modules.media.domain.value_objects.media_id import (
    EpisodeId,
    MediaId,
    MovieId,
    SeasonId,
    SeriesId,
    parse_media_id,
)
from src.modules.media.domain.value_objects.resolution import Resolution
from src.modules.media.domain.value_objects.title import Title
from src.modules.media.domain.value_objects.video_codec import VideoCodec
from src.modules.media.domain.value_objects.year import Year
from src.shared_kernel.value_objects.file_path import FilePath
from src.shared_kernel.value_objects.tracks import AudioTrack, SubtitleTrack

__all__ = [
    "AirDate",
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
