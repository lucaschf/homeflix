"""Media file probe service using ffprobe.

Discovers audio tracks, subtitle tracks (embedded and external)
from a media file, returning structured domain value objects.
"""

import functools
import json
import logging
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.modules.media.infrastructure.streaming._subprocess import SUBPROCESS_TEXT_KWARGS
from src.shared_kernel.value_objects.file_path import FilePath
from src.shared_kernel.value_objects.language_code import LanguageCode
from src.shared_kernel.value_objects.tracks import AudioTrack, SubtitleTrack

_logger = logging.getLogger(__name__)

_FFPROBE_TIMEOUT = 15  # seconds


@functools.lru_cache(maxsize=1)
def _ffprobe_path() -> str | None:
    """Return the resolved path to ffprobe, or None if not on PATH.

    Cached so that the PATH lookup runs once per process and the missing-binary
    warning is logged at most once even across thousands of probe calls.
    """
    path = shutil.which("ffprobe")
    if path is None:
        _logger.warning("ffprobe not found — probing disabled")
    return path


# Long-edge thresholds for mapping ffprobe dimensions to named resolutions.
# Tuple of (min_long_edge_pixels, resolution_name), evaluated top-down.
# Using the longer dimension handles non-standard aspect ratios (e.g. 1920x800
# cinemascope is still 1080p).
_RESOLUTION_THRESHOLDS: list[tuple[int, str]] = [
    (3000, "4K"),
    (2300, "2K"),
    (1700, "1080p"),
    (1200, "720p"),
    (800, "480p"),
    (500, "360p"),
]

# ffprobe codec_name → SubtitleTrack format
_SUBTITLE_CODEC_MAP: dict[str, str] = {
    "subrip": "srt",
    "srt": "srt",
    "ass": "ass",
    "ssa": "ass",
    "webvtt": "vtt",
    "mov_text": "srt",
    "hdmv_pgs_subtitle": "pgs",
    "pgssub": "pgs",
    "dvd_subtitle": "vobsub",
    "dvdsub": "vobsub",
}

# External subtitle file extensions
_EXTERNAL_SUB_EXTENSIONS = {".srt", ".ass", ".ssa", ".vtt", ".sub"}

# Pattern to extract language from subtitle filenames
# e.g. Movie.en.srt, Movie.English.srt, Movie.pt-BR.srt
_LANG_FILENAME_PATTERN = re.compile(
    r"\.([a-z]{2}(?:-[A-Za-z]{2})?)\.(?:srt|ass|ssa|vtt|sub)$",
    re.IGNORECASE,
)

# Common language name → ISO 639-1 mapping for filenames
_LANG_NAME_MAP: dict[str, str] = {
    "english": "en",
    "portuguese": "pt",
    "spanish": "es",
    "french": "fr",
    "german": "de",
    "italian": "it",
    "japanese": "ja",
    "korean": "ko",
    "chinese": "zh",
    "russian": "ru",
    "arabic": "ar",
    "dutch": "nl",
    "polish": "pl",
    "swedish": "sv",
    "norwegian": "no",
    "danish": "da",
    "finnish": "fi",
    "turkish": "tr",
    "greek": "el",
    "czech": "cs",
    "hungarian": "hu",
    "romanian": "ro",
    "ukrainian": "uk",
    "thai": "th",
    "vietnamese": "vi",
    "indonesian": "id",
    "malay": "ms",
    "hebrew": "he",
    "hindi": "hi",
}

_LANG_FULLNAME_PATTERN = re.compile(
    r"\.(" + "|".join(_LANG_NAME_MAP.keys()) + r")\.(?:srt|ass|ssa|vtt|sub)$",
    re.IGNORECASE,
)

# ISO 639-2 (3-letter) → ISO 639-1 (2-letter) mapping for codes commonly
# found in MKV/MP4 containers via ffprobe.
_ISO639_2_TO_1: dict[str, str] = {
    "eng": "en",
    "por": "pt",
    "spa": "es",
    "fra": "fr",
    "fre": "fr",
    "deu": "de",
    "ger": "de",
    "ita": "it",
    "jpn": "ja",
    "kor": "ko",
    "zho": "zh",
    "chi": "zh",
    "rus": "ru",
    "ara": "ar",
    "nld": "nl",
    "dut": "nl",
    "pol": "pl",
    "swe": "sv",
    "nor": "no",
    "dan": "da",
    "fin": "fi",
    "tur": "tr",
    "ell": "el",
    "gre": "el",
    "ces": "cs",
    "cze": "cs",
    "hun": "hu",
    "ron": "ro",
    "rum": "ro",
    "ukr": "uk",
    "tha": "th",
    "vie": "vi",
    "ind": "id",
    "msa": "ms",
    "may": "ms",
    "heb": "he",
    "hin": "hi",
}


@dataclass(frozen=True)
class MediaProbeResult:
    """Result of probing a media file for available tracks."""

    audio_tracks: list[AudioTrack] = field(default_factory=list)
    subtitle_tracks: list[SubtitleTrack] = field(default_factory=list)
    external_subtitles: list[SubtitleTrack] = field(default_factory=list)
    resolution: str | None = None

    @property
    def all_subtitles(self) -> list[SubtitleTrack]:
        """All subtitle tracks (embedded + external)."""
        return [*self.subtitle_tracks, *self.external_subtitles]

    @property
    def text_subtitles(self) -> list[SubtitleTrack]:
        """Only text-based subtitles that can be converted to WebVTT."""
        return [s for s in self.all_subtitles if s.is_text_based]


class MediaProbeService:
    """Probe media files for audio and subtitle track information.

    Uses ffprobe to inspect embedded streams and scans the file's
    parent directory for external subtitle files.

    Example:
        >>> service = MediaProbeService()
        >>> result = service.probe("/movies/Movie.mkv")
        >>> len(result.audio_tracks)
        2
    """

    def probe(self, file_path: str) -> MediaProbeResult:
        """Probe a media file for all available tracks.

        Args:
            file_path: Absolute path to the media file.

        Returns:
            MediaProbeResult with discovered tracks.
        """
        source = Path(file_path).resolve()
        if not source.is_file():
            _logger.warning("Cannot probe non-existent file: %s", file_path)
            return MediaProbeResult()

        streams = self._run_ffprobe(str(source))
        audio_tracks = self._parse_audio_tracks(streams)
        subtitle_tracks = self._parse_subtitle_tracks(streams)
        external_subs = self._scan_external_subtitles(source, len(subtitle_tracks))
        resolution = self._parse_resolution(streams)

        _logger.info(
            "Probed %s: %d audio, %d embedded subs, %d external subs",
            source.name,
            len(audio_tracks),
            len(subtitle_tracks),
            len(external_subs),
        )

        return MediaProbeResult(
            audio_tracks=audio_tracks,
            subtitle_tracks=subtitle_tracks,
            external_subtitles=external_subs,
            resolution=resolution,
        )

    def probe_resolution(self, file_path: str) -> str | None:
        """Detect the video resolution of a media file via ffprobe.

        Delegates to :meth:`probe` so there is a single ffprobe invocation
        path.  Returns ``None`` when ffprobe is unavailable, the file does
        not exist, has no video stream, or its dimensions fall below 360p.

        Args:
            file_path: Absolute path to the media file.

        Returns:
            A named resolution string, or ``None`` if it cannot be determined.
        """
        return self.probe(file_path).resolution

    @staticmethod
    def _run_ffprobe_video_dimensions(file_path: str) -> tuple[int, int] | None:
        """Run ffprobe to extract width/height of the first video stream."""
        ffprobe = _ffprobe_path()
        if ffprobe is None:
            return None
        try:
            result = subprocess.run(
                [
                    ffprobe,
                    "-v",
                    "error",
                    "-select_streams",
                    "v:0",
                    "-show_entries",
                    "stream=width,height",
                    "-of",
                    "json",
                    file_path,
                ],
                **SUBPROCESS_TEXT_KWARGS,
                check=False,
                timeout=_FFPROBE_TIMEOUT,
            )
            if result.returncode != 0:
                _logger.error("ffprobe failed for %s: %s", file_path, result.stderr)
                return None
            data: dict[str, Any] = json.loads(result.stdout)
            streams = data.get("streams") or []
            if not streams:
                return None
            stream = streams[0]
            width = int(stream.get("width") or 0)
            height = int(stream.get("height") or 0)
            if width <= 0 or height <= 0:
                return None
            return width, height
        except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError, ValueError) as e:
            _logger.error("ffprobe error for %s: %s", file_path, e)
            return None

    @staticmethod
    def _run_ffprobe(file_path: str) -> list[dict[str, Any]]:
        """Run ffprobe and return stream data as JSON."""
        ffprobe = _ffprobe_path()
        if ffprobe is None:
            return []
        try:
            result = subprocess.run(
                [
                    ffprobe,
                    "-v",
                    "error",
                    "-show_streams",
                    "-of",
                    "json",
                    file_path,
                ],
                **SUBPROCESS_TEXT_KWARGS,
                check=False,
                timeout=_FFPROBE_TIMEOUT,
            )
            if result.returncode != 0:
                _logger.error("ffprobe failed for %s: %s", file_path, result.stderr)
                return []
            data: dict[str, Any] = json.loads(result.stdout)
            return list(data.get("streams", []))
        except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError) as e:
            _logger.error("ffprobe error for %s: %s", file_path, e)
            return []

    @staticmethod
    def _parse_resolution(streams: list[dict[str, Any]]) -> str | None:
        """Extract the named resolution from the first valid video stream.

        Reuses the streams already loaded by ``probe`` to avoid a second
        ffprobe invocation. Skips video streams with missing or invalid
        dimensions (e.g. embedded cover art) so that a valid stream
        later in the list can still be matched.

        Returns ``None`` when no video stream has usable dimensions or
        all fall below 360p.
        """
        for stream in streams:
            if stream.get("codec_type") != "video":
                continue
            try:
                width = int(stream.get("width") or 0)
                height = int(stream.get("height") or 0)
            except (TypeError, ValueError):
                continue
            if width <= 0 or height <= 0:
                continue
            resolved = _resolution_from_dimensions(width, height)
            if resolved is not None:
                return resolved
        return None

    @staticmethod
    def _extract_language(stream: dict[str, Any]) -> str:
        """Extract ISO 639-1 language code from stream tags.

        Handles ISO 639-2/B and 639-2/T three-letter codes (e.g. ``por``,
        ``fre``, ``ger``) by mapping them to the standard two-letter code
        via ``_ISO639_2_TO_1``.
        """
        tags: dict[str, Any] = dict(stream.get("tags", {}))
        lang = str(tags.get("language", tags.get("LANGUAGE", "und")))
        lang = lang.lower().strip()

        if len(lang) == 3 and lang != "und":
            mapped = _ISO639_2_TO_1.get(lang)
            if mapped is None:
                return "un"
            lang = mapped

        if re.match(r"^[a-z]{2}$", lang):
            return lang
        return "un"

    @staticmethod
    def _parse_audio_tracks(streams: list[dict[str, Any]]) -> list[AudioTrack]:
        """Parse audio streams into AudioTrack value objects."""
        tracks = []
        audio_index = 0
        for stream in streams:
            if stream.get("codec_type") != "audio":
                continue

            disposition = stream.get("disposition", {})
            tags = stream.get("tags", {})

            lang = MediaProbeService._extract_language(stream)
            codec = stream.get("codec_name", "unknown")
            channels = int(stream.get("channels", 2))
            title = tags.get("title", tags.get("TITLE"))
            is_default = bool(disposition.get("default", 0))
            bitrate = None

            # Try to get bitrate from multiple sources
            for key in ("bit_rate", "BPS", "BPS-eng"):
                raw = stream.get(key) or tags.get(key)
                if raw and str(raw).isdigit():
                    bitrate = int(raw) // 1000  # Convert to kbps
                    break

            tracks.append(
                AudioTrack(
                    index=audio_index,
                    language=LanguageCode(lang),
                    codec=codec,
                    channels=min(channels, 16),
                    title=title,
                    is_default=is_default,
                    bitrate=bitrate,
                )
            )
            audio_index += 1

        # Ensure at least one track is default
        if tracks and not any(t.is_default for t in tracks):
            tracks[0] = AudioTrack(
                index=tracks[0].index,
                language=tracks[0].language,
                codec=tracks[0].codec,
                channels=tracks[0].channels,
                title=tracks[0].title,
                is_default=True,
                bitrate=tracks[0].bitrate,
            )

        return tracks

    @staticmethod
    def _parse_subtitle_tracks(streams: list[dict[str, Any]]) -> list[SubtitleTrack]:
        """Parse subtitle streams into SubtitleTrack value objects."""
        tracks = []
        sub_index = 0
        for stream in streams:
            if stream.get("codec_type") != "subtitle":
                continue

            disposition = stream.get("disposition", {})
            tags = stream.get("tags", {})

            codec_name = stream.get("codec_name", "unknown").lower()
            fmt = _SUBTITLE_CODEC_MAP.get(codec_name, codec_name)
            lang = MediaProbeService._extract_language(stream)
            title = tags.get("title", tags.get("TITLE"))

            tracks.append(
                SubtitleTrack(
                    index=sub_index,
                    language=LanguageCode(lang),
                    format=fmt,
                    title=title,
                    is_default=bool(disposition.get("default", 0)),
                    is_forced=bool(disposition.get("forced", 0)),
                    is_external=False,
                )
            )
            sub_index += 1

        return tracks

    @staticmethod
    def _scan_external_subtitles(
        video_path: Path,
        start_index: int,
    ) -> list[SubtitleTrack]:
        """Scan directory for external subtitle files matching the video."""
        parent = video_path.parent
        video_stem = video_path.stem.lower()

        if not parent.is_dir():
            return []

        tracks = []
        idx = start_index

        for path in sorted(parent.iterdir()):
            if path.suffix.lower() not in _EXTERNAL_SUB_EXTENSIONS:
                continue
            if not path.stem.lower().startswith(video_stem):
                continue

            lang = MediaProbeService._detect_subtitle_language(path.name)
            fmt = path.suffix.lstrip(".").lower()
            if fmt == "ssa":
                fmt = "ass"

            tracks.append(
                SubtitleTrack(
                    index=idx,
                    language=LanguageCode(lang),
                    format=fmt,
                    title=f"External ({path.suffix.upper().lstrip('.')})",
                    is_external=True,
                    file_path=FilePath(str(path)),
                )
            )
            idx += 1

        return tracks

    @staticmethod
    def _detect_subtitle_language(filename: str) -> str:
        """Detect language from subtitle filename patterns.

        Supports patterns like: Movie.en.srt, Movie.English.srt, Movie.pt-BR.srt
        """
        # Try ISO code pattern: Movie.en.srt
        match = _LANG_FILENAME_PATTERN.search(filename)
        if match:
            code = match.group(1).lower()
            # Handle pt-br → pt
            if "-" in code:
                code = code.split("-")[0]
            if len(code) == 2:
                return code

        # Try full language name: Movie.English.srt
        match = _LANG_FULLNAME_PATTERN.search(filename)
        if match:
            name = match.group(1).lower()
            return _LANG_NAME_MAP.get(name, "un")

        return "un"


def _resolution_from_dimensions(width: int, height: int) -> str | None:
    """Map raw video dimensions to a named resolution.

    Uses the longer edge to be tolerant of non-standard aspect ratios.
    """
    long_edge = max(width, height)
    for threshold, name in _RESOLUTION_THRESHOLDS:
        if long_edge >= threshold:
            return name
    return None


__all__ = ["MediaProbeResult", "MediaProbeService"]
