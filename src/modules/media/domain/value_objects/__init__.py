"""Media domain value objects."""

from src.modules.media.domain.value_objects.air_date import AirDate
from src.modules.media.domain.value_objects.cast_member import CastMember
from src.modules.media.domain.value_objects.collection import Collection
from src.modules.media.domain.value_objects.conflict_candidate import ConflictCandidate
from src.modules.media.domain.value_objects.content_rating import ContentRating
from src.modules.media.domain.value_objects.credits_detection_state import CreditsDetectionState
from src.modules.media.domain.value_objects.credits_marker import CreditsMarker, CreditsMarkerSource
from src.modules.media.domain.value_objects.duration import Duration
from src.modules.media.domain.value_objects.episode_number import EpisodeNumber
from src.modules.media.domain.value_objects.genre import Genre
from src.modules.media.domain.value_objects.hdr_format import HdrFormat
from src.modules.media.domain.value_objects.imdb_id import ImdbId
from src.modules.media.domain.value_objects.intro_detection_state import IntroDetectionState
from src.modules.media.domain.value_objects.intro_marker import IntroMarker, IntroMarkerSource
from src.modules.media.domain.value_objects.localized_metadata import (
    LocalizedField,
    LocalizedFields,
    LocalizedMetadata,
)
from src.modules.media.domain.value_objects.media_conflict_id import MediaConflictId
from src.modules.media.domain.value_objects.media_file import MediaFile
from src.modules.media.domain.value_objects.merge_policy import MergePolicy
from src.modules.media.domain.value_objects.resolution import Resolution
from src.modules.media.domain.value_objects.scan_counters import (
    EnrichCounters,
    ScanCounters,
)
from src.modules.media.domain.value_objects.scan_run_id import ScanRunId
from src.modules.media.domain.value_objects.season_number import SeasonNumber
from src.modules.media.domain.value_objects.title import Title
from src.modules.media.domain.value_objects.tmdb_id import TmdbId
from src.modules.media.domain.value_objects.video_codec import VideoCodec
from src.modules.media.domain.value_objects.year import Year
from src.shared_kernel.value_objects.file_path import FilePath
from src.shared_kernel.value_objects.image_url import ImageUrl
from src.shared_kernel.value_objects.media_id import (
    EpisodeId,
    MediaId,
    MovieId,
    SeasonId,
    SeriesId,
    parse_media_id,
)
from src.shared_kernel.value_objects.tracks import AudioTrack, SubtitleTrack

__all__ = [
    "AirDate",
    "AudioTrack",
    "CastMember",
    "Collection",
    "ConflictCandidate",
    "ContentRating",
    "CreditsDetectionState",
    "CreditsMarker",
    "CreditsMarkerSource",
    "Duration",
    "EnrichCounters",
    "EpisodeId",
    "EpisodeNumber",
    "FilePath",
    "Genre",
    "ImageUrl",
    "HdrFormat",
    "ImdbId",
    "IntroDetectionState",
    "IntroMarker",
    "IntroMarkerSource",
    "LocalizedField",
    "LocalizedFields",
    "LocalizedMetadata",
    "MediaConflictId",
    "MediaFile",
    "MediaId",
    "MergePolicy",
    "MovieId",
    "Resolution",
    "ScanCounters",
    "ScanRunId",
    "SeasonId",
    "SeasonNumber",
    "SeriesId",
    "SubtitleTrack",
    "Title",
    "TmdbId",
    "VideoCodec",
    "Year",
    "parse_media_id",
]
