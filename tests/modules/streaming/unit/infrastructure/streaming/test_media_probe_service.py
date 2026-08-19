"""Tests for MediaProbeService."""

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.modules.streaming.infrastructure.streaming.media_probe_service import (
    MediaProbeService,
    _ffprobe_path,
    _resolution_from_dimensions,
)
from src.shared_kernel.media_probe.media_probe_port import ProbeResult


@pytest.fixture(autouse=True)  # type: ignore[misc]
def _clear_ffprobe_path_cache() -> None:
    """Reset the cached ffprobe lookup so each test sees its own ``shutil.which`` patch."""
    _ffprobe_path.cache_clear()


def _ffprobe_stream(
    codec_type: str = "audio",
    codec_name: str = "aac",
    language: str = "en",
    channels: int = 2,
    default: bool = False,
    forced: bool = False,
    title: str | None = None,
    bit_rate: str | None = None,
    sample_rate: str | None = None,
    profile: str | None = None,
) -> dict[str, Any]:
    stream: dict[str, Any] = {
        "codec_type": codec_type,
        "codec_name": codec_name,
        "channels": channels,
        "disposition": {"default": 1 if default else 0, "forced": 1 if forced else 0},
        "tags": {},
    }
    if language:
        stream["tags"]["language"] = language
    if title:
        stream["tags"]["title"] = title
    if bit_rate is not None:
        stream["bit_rate"] = bit_rate
    if sample_rate is not None:
        stream["sample_rate"] = sample_rate
    if profile is not None:
        stream["profile"] = profile
    return stream


@pytest.mark.unit
class TestExtractLanguage:
    """Tests for MediaProbeService._extract_language."""

    def test_should_extract_2_letter_code(self) -> None:
        stream = {"tags": {"language": "en"}}
        assert MediaProbeService._extract_language(stream) == "en"

    def test_should_map_3_letter_eng_to_en(self) -> None:
        stream = {"tags": {"language": "eng"}}
        assert MediaProbeService._extract_language(stream) == "en"

    def test_should_map_3_letter_por_to_pt(self) -> None:
        stream = {"tags": {"language": "por"}}
        assert MediaProbeService._extract_language(stream) == "pt"

    def test_should_map_3_letter_spa_to_es(self) -> None:
        stream = {"tags": {"language": "spa"}}
        assert MediaProbeService._extract_language(stream) == "es"

    def test_should_map_3_letter_fre_to_fr(self) -> None:
        stream = {"tags": {"language": "fre"}}
        assert MediaProbeService._extract_language(stream) == "fr"

    def test_should_map_3_letter_ger_to_de(self) -> None:
        stream = {"tags": {"language": "ger"}}
        assert MediaProbeService._extract_language(stream) == "de"

    def test_should_map_3_letter_jpn_to_ja(self) -> None:
        stream = {"tags": {"language": "jpn"}}
        assert MediaProbeService._extract_language(stream) == "ja"

    def test_should_handle_uppercase(self) -> None:
        stream = {"tags": {"LANGUAGE": "EN"}}
        assert MediaProbeService._extract_language(stream) == "en"

    def test_should_return_un_for_und(self) -> None:
        stream = {"tags": {"language": "und"}}
        assert MediaProbeService._extract_language(stream) == "un"

    def test_should_return_un_for_invalid(self) -> None:
        stream = {"tags": {"language": "123"}}
        assert MediaProbeService._extract_language(stream) == "un"

    def test_should_return_un_when_no_tags(self) -> None:
        stream: dict[str, Any] = {}
        assert MediaProbeService._extract_language(stream) == "un"


@pytest.mark.unit
class TestParseAudioTracks:
    """Tests for MediaProbeService._parse_audio_tracks."""

    def test_should_parse_single_audio_track(self) -> None:
        streams = [_ffprobe_stream(codec_name="aac", language="en", channels=2)]

        tracks = MediaProbeService._parse_audio_tracks(streams)

        assert len(tracks) == 1
        assert tracks[0].codec == "aac"
        assert tracks[0].language.value == "en"
        assert tracks[0].channels == 2

    def test_should_skip_non_audio_streams(self) -> None:
        streams = [
            _ffprobe_stream(codec_type="video"),
            _ffprobe_stream(codec_type="subtitle"),
            _ffprobe_stream(codec_type="audio", codec_name="aac"),
        ]

        tracks = MediaProbeService._parse_audio_tracks(streams)

        assert len(tracks) == 1
        assert tracks[0].codec == "aac"

    def test_should_parse_multiple_audio_tracks(self) -> None:
        streams = [
            _ffprobe_stream(codec_name="aac", language="en", default=True),
            _ffprobe_stream(codec_name="ac3", language="pt", channels=6),
        ]

        tracks = MediaProbeService._parse_audio_tracks(streams)

        assert len(tracks) == 2
        assert tracks[0].is_default is True
        assert tracks[1].codec == "ac3"
        assert tracks[1].channels == 6

    def test_should_not_fabricate_default_when_none_marked(self) -> None:
        streams = [
            _ffprobe_stream(codec_name="aac", language="en", default=False),
            _ffprobe_stream(codec_name="ac3", language="pt", default=False),
        ]

        tracks = MediaProbeService._parse_audio_tracks(streams)

        # The probe reports truthfully — no fabricated default. Choosing a
        # default when the container declares none is the TrackSelector's job.
        assert all(t.is_default is False for t in tracks)

    def test_should_parse_bitrate(self) -> None:
        streams = [_ffprobe_stream(codec_name="aac", bit_rate="192000")]

        tracks = MediaProbeService._parse_audio_tracks(streams)

        assert tracks[0].bitrate == 192  # kbps

    def test_should_parse_title(self) -> None:
        streams = [_ffprobe_stream(codec_name="aac", title="English Stereo")]

        tracks = MediaProbeService._parse_audio_tracks(streams)

        assert tracks[0].title == "English Stereo"

    def test_should_cap_channels_at_16(self) -> None:
        streams = [_ffprobe_stream(codec_name="aac", channels=20)]

        tracks = MediaProbeService._parse_audio_tracks(streams)

        assert tracks[0].channels == 16

    def test_should_parse_sample_rate_and_profile(self) -> None:
        streams = [_ffprobe_stream(codec_name="aac", sample_rate="48000", profile="LC")]

        tracks = MediaProbeService._parse_audio_tracks(streams)

        assert tracks[0].sample_rate == 48000
        assert tracks[0].profile == "LC"

    def test_should_default_sample_rate_and_profile_to_none(self) -> None:
        # ffprobe omits these on some containers; absence must not crash.
        streams = [_ffprobe_stream(codec_name="ac3")]

        tracks = MediaProbeService._parse_audio_tracks(streams)

        assert tracks[0].sample_rate is None
        assert tracks[0].profile is None

    def test_should_return_empty_for_no_audio(self) -> None:
        tracks = MediaProbeService._parse_audio_tracks([])
        assert tracks == []


@pytest.mark.unit
class TestParseSubtitleTracks:
    """Tests for MediaProbeService._parse_subtitle_tracks."""

    def test_should_parse_embedded_subrip(self) -> None:
        streams = [
            {
                "codec_type": "subtitle",
                "codec_name": "subrip",
                "disposition": {"default": 1},
                "tags": {"language": "en"},
            }
        ]

        tracks = MediaProbeService._parse_subtitle_tracks(streams)

        assert len(tracks) == 1
        assert tracks[0].format == "srt"
        assert tracks[0].is_default is True
        assert tracks[0].is_external is False

    def test_should_map_codec_names(self) -> None:
        streams = [
            {
                "codec_type": "subtitle",
                "codec_name": "webvtt",
                "disposition": {},
                "tags": {"language": "en"},
            },
            {
                "codec_type": "subtitle",
                "codec_name": "hdmv_pgs_subtitle",
                "disposition": {},
                "tags": {"language": "pt"},
            },
        ]

        tracks = MediaProbeService._parse_subtitle_tracks(streams)

        assert tracks[0].format == "vtt"
        assert tracks[1].format == "pgs"

    def test_should_mark_forced_subtitles(self) -> None:
        streams = [
            {
                "codec_type": "subtitle",
                "codec_name": "subrip",
                "disposition": {"forced": 1},
                "tags": {"language": "en"},
            }
        ]

        tracks = MediaProbeService._parse_subtitle_tracks(streams)

        assert tracks[0].is_forced is True

    def test_should_skip_non_subtitle_streams(self) -> None:
        streams = [
            {"codec_type": "audio"},
            {"codec_type": "video"},
        ]

        tracks = MediaProbeService._parse_subtitle_tracks(streams)

        assert tracks == []

    def test_should_use_raw_codec_when_unknown(self) -> None:
        streams = [
            {
                "codec_type": "subtitle",
                "codec_name": "unknown_format",
                "disposition": {},
                "tags": {"language": "en"},
            }
        ]

        tracks = MediaProbeService._parse_subtitle_tracks(streams)

        assert tracks[0].format == "unknown_format"


@pytest.mark.unit
class TestDetectSubtitleLanguage:
    """Tests for MediaProbeService._detect_subtitle_language."""

    def test_should_detect_iso_code(self) -> None:
        assert MediaProbeService._detect_subtitle_language("Movie.en.srt") == "en"

    def test_should_detect_pt_br(self) -> None:
        assert MediaProbeService._detect_subtitle_language("Movie.pt-BR.srt") == "pt"

    def test_should_detect_full_english(self) -> None:
        assert MediaProbeService._detect_subtitle_language("Movie.English.srt") == "en"

    def test_should_detect_full_portuguese(self) -> None:
        assert MediaProbeService._detect_subtitle_language("Movie.Portuguese.srt") == "pt"

    def test_should_detect_full_japanese(self) -> None:
        assert MediaProbeService._detect_subtitle_language("Movie.Japanese.srt") == "ja"

    def test_should_return_un_for_unknown(self) -> None:
        assert MediaProbeService._detect_subtitle_language("Movie.srt") == "un"

    def test_should_handle_ass_format(self) -> None:
        assert MediaProbeService._detect_subtitle_language("Movie.en.ass") == "en"


@pytest.mark.unit
class TestScanExternalSubtitles:
    """Tests for MediaProbeService._scan_external_subtitles."""

    def test_should_find_matching_subtitle_files(self, tmp_path: Path) -> None:
        video = tmp_path / "Movie.mkv"
        video.touch()
        (tmp_path / "Movie.en.srt").touch()
        (tmp_path / "Movie.pt.srt").touch()

        tracks = MediaProbeService._scan_external_subtitles(video, start_index=0)

        assert len(tracks) == 2
        langs = {t.language.value for t in tracks}
        assert langs == {"en", "pt"}

    def test_should_skip_non_matching_files(self, tmp_path: Path) -> None:
        video = tmp_path / "Movie.mkv"
        video.touch()
        (tmp_path / "Other.en.srt").touch()

        tracks = MediaProbeService._scan_external_subtitles(video, start_index=0)

        assert tracks == []

    def test_should_skip_files_with_wrong_extension(self, tmp_path: Path) -> None:
        video = tmp_path / "Movie.mkv"
        video.touch()
        (tmp_path / "Movie.en.txt").touch()

        tracks = MediaProbeService._scan_external_subtitles(video, start_index=0)

        assert tracks == []

    def test_should_start_indexing_from_given_index(self, tmp_path: Path) -> None:
        video = tmp_path / "Movie.mkv"
        video.touch()
        (tmp_path / "Movie.en.srt").touch()

        tracks = MediaProbeService._scan_external_subtitles(video, start_index=5)

        assert tracks[0].index == 5

    def test_should_return_empty_when_directory_missing(self, tmp_path: Path) -> None:
        # Point to a non-existent directory
        video = tmp_path / "missing" / "Movie.mkv"

        tracks = MediaProbeService._scan_external_subtitles(video, start_index=0)

        assert tracks == []

    def test_should_normalize_ssa_to_ass(self, tmp_path: Path) -> None:
        video = tmp_path / "Movie.mkv"
        video.touch()
        (tmp_path / "Movie.en.ssa").touch()

        tracks = MediaProbeService._scan_external_subtitles(video, start_index=0)

        assert tracks[0].format == "ass"


@pytest.mark.unit
class TestProbeResult:
    """Tests for ProbeResult properties."""

    def test_all_subtitles_should_combine_embedded_and_external(self) -> None:
        from src.shared_kernel.value_objects.file_path import FilePath
        from src.shared_kernel.value_objects.language_code import LanguageCode
        from src.shared_kernel.value_objects.tracks import SubtitleTrack

        embedded = SubtitleTrack(
            index=0, language=LanguageCode("en"), format="srt", is_external=False
        )
        external = SubtitleTrack(
            index=1,
            language=LanguageCode("pt"),
            format="srt",
            is_external=True,
            file_path=FilePath("/movies/Movie.pt.srt"),
        )
        result = ProbeResult(
            subtitle_tracks=[embedded],
            external_subtitles=[external],
        )

        assert len(result.all_subtitles) == 2

    def test_text_subtitles_should_exclude_image_based(self) -> None:
        from src.shared_kernel.value_objects.language_code import LanguageCode
        from src.shared_kernel.value_objects.tracks import SubtitleTrack

        text = SubtitleTrack(index=0, language=LanguageCode("en"), format="srt")
        image = SubtitleTrack(index=1, language=LanguageCode("en"), format="pgs")

        result = ProbeResult(subtitle_tracks=[text, image])

        assert len(result.text_subtitles) == 1
        assert result.text_subtitles[0].format == "srt"


@pytest.mark.unit
class TestMediaProbeServiceRunFfprobe:
    """Tests for MediaProbeService._run_ffprobe with mocked subprocess."""

    @patch(
        "src.modules.streaming.infrastructure.streaming.media_probe_service.shutil.which",
        return_value=None,
    )
    def test_should_return_empty_when_ffprobe_missing(self, _which: MagicMock) -> None:
        result = MediaProbeService._run_ffprobe("/path/to/movie.mkv")
        assert result == {}

    @patch("src.modules.streaming.infrastructure.streaming.media_probe_service.subprocess.run")
    @patch(
        "src.modules.streaming.infrastructure.streaming.media_probe_service.shutil.which",
        return_value="/usr/bin/ffprobe",
    )
    def test_should_return_streams_on_success(self, _which: MagicMock, mock_run: MagicMock) -> None:
        streams = [{"codec_type": "audio", "codec_name": "aac"}]
        payload = {"streams": streams, "format": {"duration": "120.5"}}
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps(payload)
        mock_run.return_value = mock_result

        result = MediaProbeService._run_ffprobe("/path/to/movie.mkv")

        assert result == payload

    @patch("src.modules.streaming.infrastructure.streaming.media_probe_service.subprocess.run")
    @patch(
        "src.modules.streaming.infrastructure.streaming.media_probe_service.shutil.which",
        return_value="/usr/bin/ffprobe",
    )
    def test_should_return_empty_on_non_zero_exit(
        self, _which: MagicMock, mock_run: MagicMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "error"
        mock_run.return_value = mock_result

        result = MediaProbeService._run_ffprobe("/path/to/movie.mkv")

        assert result == {}

    @patch(
        "src.modules.streaming.infrastructure.streaming.media_probe_service.subprocess.run",
        side_effect=OSError("failed"),
    )
    @patch(
        "src.modules.streaming.infrastructure.streaming.media_probe_service.shutil.which",
        return_value="/usr/bin/ffprobe",
    )
    def test_should_return_empty_on_os_error(self, _which: MagicMock, _run: MagicMock) -> None:
        result = MediaProbeService._run_ffprobe("/path/to/movie.mkv")
        assert result == {}


@pytest.mark.unit
class TestMediaProbeServiceParseDuration:
    """Tests for MediaProbeService._parse_duration."""

    def test_prefers_format_duration(self) -> None:
        data = {"format": {"duration": "5430.6"}, "streams": [{"duration": "10.0"}]}
        assert MediaProbeService._parse_duration(data) == 5431

    def test_falls_back_to_longest_stream(self) -> None:
        data = {"streams": [{"duration": "100.0"}, {"duration": "2700.4"}]}
        assert MediaProbeService._parse_duration(data) == 2700

    def test_none_when_no_duration(self) -> None:
        assert MediaProbeService._parse_duration({"streams": [{}]}) is None

    def test_ignores_zero_and_garbage(self) -> None:
        data = {"format": {"duration": "0"}, "streams": [{"duration": "N/A"}]}
        assert MediaProbeService._parse_duration(data) is None


@pytest.mark.unit
class TestMediaProbeServiceProbe:
    """Tests for the top-level probe method."""

    def test_should_return_empty_for_missing_file(self, tmp_path: Path) -> None:
        service = MediaProbeService()
        missing = tmp_path / "missing.mkv"

        result = service.probe(str(missing))

        assert result.audio_tracks == []
        assert result.subtitle_tracks == []
        assert result.external_subtitles == []


@pytest.mark.unit
class TestResolutionFromDimensions:
    """Tests for the dimension-to-named-resolution mapping."""

    @pytest.mark.parametrize(
        ("width", "height", "expected"),
        [
            (3840, 2160, "4K"),
            (4096, 2160, "4K"),
            (2560, 1440, "2K"),
            (1920, 1080, "1080p"),
            (1920, 800, "1080p"),  # cinemascope still 1080p by long edge
            (1280, 720, "720p"),
            (854, 480, "480p"),
            (640, 360, "360p"),
        ],
    )
    def test_should_map_known_dimensions(self, width: int, height: int, expected: str) -> None:
        assert _resolution_from_dimensions(width, height) == expected

    def test_should_return_none_for_below_360p(self) -> None:
        assert _resolution_from_dimensions(320, 240) is None

    def test_should_return_none_for_zero_dimensions(self) -> None:
        assert _resolution_from_dimensions(0, 0) is None


@pytest.mark.unit
class TestProbeResolution:
    """Tests for MediaProbeService.probe_resolution."""

    def test_should_return_none_for_missing_file(self, tmp_path: Path) -> None:
        service = MediaProbeService()
        missing = tmp_path / "missing.mkv"

        assert service.probe_resolution(str(missing)) is None

    @patch(
        "src.modules.streaming.infrastructure.streaming.media_probe_service.shutil.which",
        return_value=None,
    )
    def test_should_return_none_when_ffprobe_missing(
        self, _which: MagicMock, tmp_path: Path
    ) -> None:
        video = tmp_path / "movie.mkv"
        video.touch()
        service = MediaProbeService()

        assert service.probe_resolution(str(video)) is None

    @patch("src.modules.streaming.infrastructure.streaming.media_probe_service.subprocess.run")
    @patch(
        "src.modules.streaming.infrastructure.streaming.media_probe_service.shutil.which",
        return_value="/usr/bin/ffprobe",
    )
    def test_should_return_resolution_from_dimensions(
        self, _which: MagicMock, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        video = tmp_path / "movie.mkv"
        video.touch()
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps(
            {"streams": [{"codec_type": "video", "width": 1920, "height": 1080}]}
        )
        mock_run.return_value = mock_result
        service = MediaProbeService()

        assert service.probe_resolution(str(video)) == "1080p"

    @patch("src.modules.streaming.infrastructure.streaming.media_probe_service.subprocess.run")
    @patch(
        "src.modules.streaming.infrastructure.streaming.media_probe_service.shutil.which",
        return_value="/usr/bin/ffprobe",
    )
    def test_should_return_none_when_no_video_stream(
        self, _which: MagicMock, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        video = tmp_path / "movie.mkv"
        video.touch()
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({"streams": []})
        mock_run.return_value = mock_result
        service = MediaProbeService()

        assert service.probe_resolution(str(video)) is None

    @patch("src.modules.streaming.infrastructure.streaming.media_probe_service.subprocess.run")
    @patch(
        "src.modules.streaming.infrastructure.streaming.media_probe_service.shutil.which",
        return_value="/usr/bin/ffprobe",
    )
    def test_should_return_none_on_ffprobe_failure(
        self, _which: MagicMock, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        video = tmp_path / "movie.mkv"
        video.touch()
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "error"
        mock_run.return_value = mock_result
        service = MediaProbeService()

        assert service.probe_resolution(str(video)) is None


@pytest.mark.unit
class TestFfprobePathCache:
    """Tests for the cached ffprobe lookup helper."""

    @patch(
        "src.modules.streaming.infrastructure.streaming.media_probe_service.shutil.which",
        return_value=None,
    )
    def test_should_log_missing_warning_only_once(
        self,
        mock_which: MagicMock,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        with caplog.at_level("WARNING"):
            for _ in range(5):
                MediaProbeService._run_ffprobe("/path/to/movie.mkv")
                MediaProbeService._run_ffprobe_video_dimensions("/path/to/movie.mkv")

        warnings = [r for r in caplog.records if "ffprobe not found" in r.message]
        assert len(warnings) == 1
        assert mock_which.call_count == 1

    @patch(
        "src.modules.streaming.infrastructure.streaming.media_probe_service.shutil.which",
        return_value="/usr/bin/ffprobe",
    )
    def test_should_cache_resolved_path(self, mock_which: MagicMock) -> None:
        for _ in range(5):
            assert _ffprobe_path() == "/usr/bin/ffprobe"

        assert mock_which.call_count == 1
