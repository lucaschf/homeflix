"""Media file probe service using ffprobe.

Discovers audio tracks, subtitle tracks (embedded and external)
from a media file, returning structured domain value objects.
"""

import json
import logging
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.shared_kernel.value_objects.file_path import FilePath
from src.shared_kernel.value_objects.language_code import LanguageCode
from src.shared_kernel.value_objects.tracks import AudioTrack, SubtitleTrack

_logger = logging.getLogger(__name__)

_FFPROBE_TIMEOUT = 15  # seconds

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


@dataclass(frozen=True)
class MediaProbeResult:
    """Result of probing a media file for available tracks."""

    audio_tracks: list[AudioTrack] = field(default_factory=list)
    subtitle_tracks: list[SubtitleTrack] = field(default_factory=list)
    external_subtitles: list[SubtitleTrack] = field(default_factory=list)

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
        )

    @staticmethod
    def _run_ffprobe(file_path: str) -> list[dict[str, Any]]:
        """Run ffprobe and return stream data as JSON."""
        if not shutil.which("ffprobe"):
            _logger.warning("ffprobe not found — cannot probe %s", file_path)
            return []
        try:
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_streams",
                    "-of",
                    "json",
                    file_path,
                ],
                capture_output=True,
                text=True,
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
    def _extract_language(stream: dict[str, Any]) -> str:
        """Extract ISO 639-1 language code from stream tags."""
        tags: dict[str, Any] = dict(stream.get("tags", {}))
        lang = str(tags.get("language", tags.get("LANGUAGE", "und")))
        lang = lang.lower().strip()

        # Handle 3-letter codes by taking first 2
        if len(lang) == 3 and lang != "und":
            lang = lang[:2]

        # Validate: must be 2 lowercase letters
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


__all__ = ["MediaProbeResult", "MediaProbeService"]
