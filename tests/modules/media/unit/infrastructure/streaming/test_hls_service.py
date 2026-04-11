"""Tests for HlsService."""

import hashlib
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.modules.media.infrastructure.streaming.hls_service import (
    HlsService,
    _primary_audio_index,
)
from src.modules.media.infrastructure.streaming.media_probe_service import (
    MediaProbeResult,
    MediaProbeService,
)
from src.shared_kernel.value_objects.language_code import LanguageCode
from src.shared_kernel.value_objects.tracks import AudioTrack, SubtitleTrack


def _make_audio_track(
    index: int = 0,
    lang: str = "en",
    codec: str = "aac",
    channels: int = 2,
    is_default: bool = True,
    title: str | None = None,
) -> AudioTrack:
    return AudioTrack(
        index=index,
        language=LanguageCode(lang),
        codec=codec,
        channels=channels,
        is_default=is_default,
        title=title,
    )


def _make_subtitle_track(
    index: int = 0,
    lang: str = "en",
    fmt: str = "srt",
    is_forced: bool = False,
) -> SubtitleTrack:
    return SubtitleTrack(
        index=index,
        language=LanguageCode(lang),
        format=fmt,
        is_forced=is_forced,
    )


@pytest.mark.unit
class TestPrimaryAudioIndex:
    """Tests for the _primary_audio_index helper."""

    def test_should_return_first_track_index(self) -> None:
        probe = MediaProbeResult(
            audio_tracks=[_make_audio_track(index=2), _make_audio_track(index=5)],
        )
        assert _primary_audio_index(probe) == 2

    def test_should_return_zero_when_no_tracks(self) -> None:
        probe = MediaProbeResult(audio_tracks=[])
        assert _primary_audio_index(probe) == 0


@pytest.mark.unit
class TestHlsServiceInit:
    """Tests for HlsService initialization."""

    def test_should_create_cache_directory(self, tmp_path: Path) -> None:
        cache = tmp_path / "hls"
        HlsService(cache_dir=str(cache))
        assert cache.is_dir()

    def test_should_accept_custom_probe_service(self, tmp_path: Path) -> None:
        custom_probe = MagicMock(spec=MediaProbeService)
        service = HlsService(cache_dir=str(tmp_path / "hls"), probe_service=custom_probe)
        assert service._probe is custom_probe


@pytest.mark.unit
class TestHlsServiceGetPathHash:
    """Tests for get_path_hash."""

    def test_should_return_md5_hash(self, tmp_path: Path) -> None:
        service = HlsService(cache_dir=str(tmp_path / "hls"))
        file_path = "/movies/inception.mkv"

        result = service.get_path_hash(file_path)

        expected = hashlib.md5(file_path.encode()).hexdigest()
        assert result == expected

    def test_should_be_deterministic(self, tmp_path: Path) -> None:
        service = HlsService(cache_dir=str(tmp_path / "hls"))
        path = "/movies/test.mkv"
        assert service.get_path_hash(path) == service.get_path_hash(path)

    def test_should_differ_for_different_paths(self, tmp_path: Path) -> None:
        service = HlsService(cache_dir=str(tmp_path / "hls"))
        assert service.get_path_hash("/a.mkv") != service.get_path_hash("/b.mkv")

    def test_should_match_default_hash_when_start_seconds_is_zero(self, tmp_path: Path) -> None:
        service = HlsService(cache_dir=str(tmp_path / "hls"))
        path = "/movies/test.mkv"
        assert service.get_path_hash(path) == service.get_path_hash(path, 0.0)

    def test_should_differ_for_different_start_seconds(self, tmp_path: Path) -> None:
        service = HlsService(cache_dir=str(tmp_path / "hls"))
        path = "/movies/test.mkv"
        hash_zero = service.get_path_hash(path, 0.0)
        hash_middle = service.get_path_hash(path, 1800.0)
        hash_end = service.get_path_hash(path, 5400.0)
        assert hash_zero != hash_middle
        assert hash_middle != hash_end
        assert hash_zero != hash_end

    def test_should_be_deterministic_with_start_seconds(self, tmp_path: Path) -> None:
        service = HlsService(cache_dir=str(tmp_path / "hls"))
        path = "/movies/test.mkv"
        assert service.get_path_hash(path, 1234.5) == service.get_path_hash(path, 1234.5)


@pytest.mark.unit
class TestHlsServiceGetFileByHash:
    """Tests for get_file_by_hash with path traversal protection."""

    def test_should_return_file_when_exists(self, tmp_path: Path) -> None:
        service = HlsService(cache_dir=str(tmp_path))
        hash_dir = tmp_path / "abc123"
        hash_dir.mkdir()
        target = hash_dir / "segment_0000.ts"
        target.write_text("data")

        result = service.get_file_by_hash("abc123", "segment_0000.ts")

        assert result == target

    def test_should_return_none_when_file_missing(self, tmp_path: Path) -> None:
        service = HlsService(cache_dir=str(tmp_path))
        (tmp_path / "abc123").mkdir()

        result = service.get_file_by_hash("abc123", "missing.ts")

        assert result is None

    def test_should_block_path_traversal(self, tmp_path: Path) -> None:
        service = HlsService(cache_dir=str(tmp_path))
        (tmp_path / "abc123").mkdir()
        secret = tmp_path / "secret.txt"
        secret.write_text("secret")

        result = service.get_file_by_hash("abc123", "../secret.txt")

        assert result is None

    def test_should_return_nested_file(self, tmp_path: Path) -> None:
        service = HlsService(cache_dir=str(tmp_path))
        nested = tmp_path / "abc" / "video"
        nested.mkdir(parents=True)
        target = nested / "playlist.m3u8"
        target.write_text("#EXTM3U")

        result = service.get_file_by_hash("abc", "video/playlist.m3u8")

        assert result == target


@pytest.mark.unit
class TestHlsServiceIsComplete:
    """Tests for is_complete."""

    def test_should_return_false_when_playlist_missing(self, tmp_path: Path) -> None:
        service = HlsService(cache_dir=str(tmp_path))

        assert service.is_complete("abc123") is False

    def test_should_return_true_when_endlist_marker_present(self, tmp_path: Path) -> None:
        service = HlsService(cache_dir=str(tmp_path))
        video_dir = tmp_path / "abc123" / "video"
        video_dir.mkdir(parents=True)
        (video_dir / "playlist.m3u8").write_text(
            "#EXTM3U\n#EXTINF:10,\nsegment_0000.ts\n#EXT-X-ENDLIST\n"
        )

        assert service.is_complete("abc123") is True

    def test_should_return_false_when_endlist_marker_missing(self, tmp_path: Path) -> None:
        service = HlsService(cache_dir=str(tmp_path))
        video_dir = tmp_path / "abc123" / "video"
        video_dir.mkdir(parents=True)
        (video_dir / "playlist.m3u8").write_text("#EXTM3U\n#EXTINF:10,\nsegment_0000.ts\n")

        assert service.is_complete("abc123") is False

    def test_should_fallback_to_flat_playlist(self, tmp_path: Path) -> None:
        service = HlsService(cache_dir=str(tmp_path))
        hash_dir = tmp_path / "abc123"
        hash_dir.mkdir()
        (hash_dir / "playlist.m3u8").write_text(
            "#EXTM3U\n#EXTINF:10,\nsegment_0000.ts\n#EXT-X-ENDLIST\n"
        )

        assert service.is_complete("abc123") is True


@pytest.mark.unit
class TestHlsServiceGetMasterPlaylist:
    """Tests for get_master_playlist."""

    def test_should_return_master_playlist_content(self, tmp_path: Path) -> None:
        service = HlsService(cache_dir=str(tmp_path))
        hash_dir = tmp_path / "abc"
        hash_dir.mkdir()
        content = "#EXTM3U\n#EXT-X-VERSION:3\n"
        (hash_dir / "master.m3u8").write_text(content)

        result = service.get_master_playlist("abc")

        assert result == content

    def test_should_fallback_to_legacy_playlist(self, tmp_path: Path) -> None:
        service = HlsService(cache_dir=str(tmp_path))
        hash_dir = tmp_path / "abc"
        hash_dir.mkdir()
        content = "#EXTM3U\n#EXT-X-VERSION:3\n"
        (hash_dir / "playlist.m3u8").write_text(content)

        result = service.get_master_playlist("abc")

        assert result == content

    def test_should_return_none_when_missing(self, tmp_path: Path) -> None:
        service = HlsService(cache_dir=str(tmp_path))
        assert service.get_master_playlist("missing") is None


@pytest.mark.unit
class TestHlsServiceGetCachedTracks:
    """Tests for get_cached_tracks."""

    def test_should_return_parsed_json(self, tmp_path: Path) -> None:
        service = HlsService(cache_dir=str(tmp_path))
        hash_dir = tmp_path / "abc"
        hash_dir.mkdir()
        data = {"audio_tracks": [{"index": 0, "language": "en"}]}
        (hash_dir / "tracks.json").write_text(json.dumps(data))

        result = service.get_cached_tracks("abc")

        assert result == data

    def test_should_return_none_when_file_missing(self, tmp_path: Path) -> None:
        service = HlsService(cache_dir=str(tmp_path))
        assert service.get_cached_tracks("missing") is None

    def test_should_return_none_on_invalid_json(self, tmp_path: Path) -> None:
        service = HlsService(cache_dir=str(tmp_path))
        hash_dir = tmp_path / "abc"
        hash_dir.mkdir()
        (hash_dir / "tracks.json").write_text("not json")

        assert service.get_cached_tracks("abc") is None


@pytest.mark.unit
class TestHlsServiceBuildAudioCmd:
    """Tests for _build_audio_cmd."""

    def test_should_include_input_file(self, tmp_path: Path) -> None:
        cmd = HlsService._build_audio_cmd("/movies/test.mkv", tmp_path, audio_index=1)

        assert "-i" in cmd
        assert "/movies/test.mkv" in cmd

    def test_should_map_to_correct_audio_stream(self, tmp_path: Path) -> None:
        cmd = HlsService._build_audio_cmd("/movies/test.mkv", tmp_path, audio_index=2)

        assert "0:a:2" in cmd

    def test_should_disable_video_and_subtitle(self, tmp_path: Path) -> None:
        cmd = HlsService._build_audio_cmd("/movies/test.mkv", tmp_path, audio_index=0)

        assert "-vn" in cmd
        assert "-sn" in cmd

    def test_should_use_aac_codec(self, tmp_path: Path) -> None:
        cmd = HlsService._build_audio_cmd("/movies/test.mkv", tmp_path, audio_index=0)

        assert "aac" in cmd

    def test_should_not_include_ss_when_start_is_zero(self, tmp_path: Path) -> None:
        cmd = HlsService._build_audio_cmd(
            "/movies/test.mkv", tmp_path, audio_index=0, start_seconds=0.0
        )

        assert "-ss" not in cmd

    def test_should_include_ss_before_input_when_start_is_set(self, tmp_path: Path) -> None:
        cmd = HlsService._build_audio_cmd(
            "/movies/test.mkv", tmp_path, audio_index=0, start_seconds=1800.0
        )

        assert "-ss" in cmd
        ss_idx = cmd.index("-ss")
        i_idx = cmd.index("-i")
        assert ss_idx < i_idx, "-ss must come before -i for fast seek"
        assert cmd[ss_idx + 1] == "1800.0"


@pytest.mark.unit
class TestHlsServiceBuildVideoCmd:
    """Tests for _build_video_cmd with mocked codec probe."""

    def test_should_copy_video_for_h264(self, tmp_path: Path) -> None:
        service = HlsService(cache_dir=str(tmp_path / "cache"))
        probe = MediaProbeResult(audio_tracks=[_make_audio_track()])

        with patch.object(HlsService, "_probe_video_codec", return_value="h264"):
            cmd = service._build_video_cmd("/movies/test.mkv", tmp_path, probe)

        assert "copy" in cmd
        assert "libx264" not in cmd

    def test_should_transcode_non_h264(self, tmp_path: Path) -> None:
        service = HlsService(cache_dir=str(tmp_path / "cache"))
        probe = MediaProbeResult(audio_tracks=[_make_audio_track()])

        with patch.object(HlsService, "_probe_video_codec", return_value="hevc"):
            cmd = service._build_video_cmd("/movies/test.mkv", tmp_path, probe)

        assert "libx264" in cmd

    def test_should_map_primary_audio_track(self, tmp_path: Path) -> None:
        service = HlsService(cache_dir=str(tmp_path / "cache"))
        probe = MediaProbeResult(
            audio_tracks=[_make_audio_track(index=3)],
        )

        with patch.object(HlsService, "_probe_video_codec", return_value="h264"):
            cmd = service._build_video_cmd("/movies/test.mkv", tmp_path, probe)

        assert "0:a:3" in cmd

    def test_should_not_include_ss_when_start_is_zero(self, tmp_path: Path) -> None:
        service = HlsService(cache_dir=str(tmp_path / "cache"))
        probe = MediaProbeResult(audio_tracks=[_make_audio_track()])

        with patch.object(HlsService, "_probe_video_codec", return_value="h264"):
            cmd = service._build_video_cmd("/movies/test.mkv", tmp_path, probe, start_seconds=0.0)

        assert "-ss" not in cmd

    def test_should_include_ss_before_input_when_start_is_set(self, tmp_path: Path) -> None:
        service = HlsService(cache_dir=str(tmp_path / "cache"))
        probe = MediaProbeResult(audio_tracks=[_make_audio_track()])

        with patch.object(HlsService, "_probe_video_codec", return_value="h264"):
            cmd = service._build_video_cmd(
                "/movies/test.mkv", tmp_path, probe, start_seconds=5400.0
            )

        assert "-ss" in cmd
        ss_idx = cmd.index("-ss")
        i_idx = cmd.index("-i")
        assert ss_idx < i_idx, "-ss must come before -i for fast seek"
        assert cmd[ss_idx + 1] == "5400.0"


@pytest.mark.unit
class TestHlsServiceBuildMasterPlaylist:
    """Tests for _build_master_playlist."""

    def test_should_write_master_m3u8(self, tmp_path: Path) -> None:
        probe = MediaProbeResult(audio_tracks=[_make_audio_track()])

        HlsService._build_master_playlist(tmp_path, probe)

        master = tmp_path / "master.m3u8"
        assert master.is_file()
        content = master.read_text()
        assert "#EXTM3U" in content
        assert "video/playlist.m3u8" in content

    def test_should_include_ext_media_for_alt_audio(self, tmp_path: Path) -> None:
        probe = MediaProbeResult(
            audio_tracks=[
                _make_audio_track(index=0, lang="en", is_default=True),
                _make_audio_track(index=1, lang="pt", is_default=False),
            ],
        )

        HlsService._build_master_playlist(tmp_path, probe)

        content = (tmp_path / "master.m3u8").read_text()
        assert "#EXT-X-MEDIA:TYPE=AUDIO" in content
        assert 'LANGUAGE="en"' in content
        assert 'LANGUAGE="pt"' in content
        assert 'URI="audio_1/playlist.m3u8"' in content

    def test_should_include_ext_media_for_subtitles(self, tmp_path: Path) -> None:
        probe = MediaProbeResult(
            audio_tracks=[_make_audio_track()],
            subtitle_tracks=[_make_subtitle_track(index=0, lang="en", fmt="srt")],
        )

        HlsService._build_master_playlist(tmp_path, probe)

        content = (tmp_path / "master.m3u8").read_text()
        assert "#EXT-X-MEDIA:TYPE=SUBTITLES" in content
        assert 'URI="sub_0/playlist.m3u8"' in content

    def test_should_skip_image_based_subtitles(self, tmp_path: Path) -> None:
        probe = MediaProbeResult(
            audio_tracks=[_make_audio_track()],
            subtitle_tracks=[_make_subtitle_track(index=0, lang="en", fmt="pgs")],
        )

        HlsService._build_master_playlist(tmp_path, probe)

        content = (tmp_path / "master.m3u8").read_text()
        assert 'URI="sub_0/playlist.m3u8"' not in content

    def test_should_mark_forced_subtitles(self, tmp_path: Path) -> None:
        probe = MediaProbeResult(
            audio_tracks=[_make_audio_track()],
            subtitle_tracks=[
                _make_subtitle_track(index=0, lang="en", fmt="srt", is_forced=True),
            ],
        )

        HlsService._build_master_playlist(tmp_path, probe)

        content = (tmp_path / "master.m3u8").read_text()
        assert "FORCED=YES" in content


@pytest.mark.unit
class TestHlsServiceSaveAndDeserializeProbe:
    """Tests for probe cache serialization round-trip."""

    def test_should_save_probe_as_json(self, tmp_path: Path) -> None:
        probe = MediaProbeResult(
            audio_tracks=[_make_audio_track(index=0, lang="en", codec="aac")],
            subtitle_tracks=[_make_subtitle_track(index=0, lang="en", fmt="srt")],
        )

        HlsService._save_probe_cache(tmp_path, probe)

        tracks_file = tmp_path / "tracks.json"
        assert tracks_file.is_file()
        data = json.loads(tracks_file.read_text())
        assert len(data["audio_tracks"]) == 1
        assert data["audio_tracks"][0]["language"] == "en"

    def test_should_round_trip_probe_cache(self, tmp_path: Path) -> None:
        probe = MediaProbeResult(
            audio_tracks=[
                _make_audio_track(index=0, lang="en", codec="aac", title="English"),
                _make_audio_track(index=1, lang="pt", codec="ac3", channels=6),
            ],
            subtitle_tracks=[_make_subtitle_track(index=0, lang="en", fmt="srt")],
        )

        HlsService._save_probe_cache(tmp_path, probe)
        data = json.loads((tmp_path / "tracks.json").read_text())
        result = HlsService._deserialize_probe(data)

        assert len(result.audio_tracks) == 2
        assert result.audio_tracks[0].title == "English"
        assert result.audio_tracks[1].channels == 6
        assert len(result.subtitle_tracks) == 1


@pytest.mark.unit
class TestHlsServiceProbeTracks:
    """Tests for probe_tracks using cache."""

    def test_should_return_cached_tracks_when_available(self, tmp_path: Path) -> None:
        probe_mock = MagicMock(spec=MediaProbeService)
        service = HlsService(cache_dir=str(tmp_path), probe_service=probe_mock)

        file_path = "/movies/test.mkv"
        path_hash = service.get_path_hash(file_path)
        hash_dir = tmp_path / path_hash
        hash_dir.mkdir()
        (hash_dir / "tracks.json").write_text(
            json.dumps({"audio_tracks": [], "subtitle_tracks": []})
        )

        result = service.probe_tracks(file_path)

        assert result.audio_tracks == []
        probe_mock.probe.assert_not_called()

    def test_should_call_probe_service_when_no_cache(self, tmp_path: Path) -> None:
        probe_mock = MagicMock(spec=MediaProbeService)
        probe_mock.probe.return_value = MediaProbeResult(audio_tracks=[_make_audio_track()])
        service = HlsService(cache_dir=str(tmp_path), probe_service=probe_mock)

        result = service.probe_tracks("/movies/test.mkv")

        probe_mock.probe.assert_called_once_with("/movies/test.mkv")
        assert len(result.audio_tracks) == 1


@pytest.mark.unit
class TestHlsServiceClearCache:
    """Tests for clear_cache."""

    def test_should_clear_specific_file_cache(self, tmp_path: Path) -> None:
        service = HlsService(cache_dir=str(tmp_path))
        file_path = "/movies/test.mkv"
        path_hash = service.get_path_hash(file_path)
        (tmp_path / path_hash).mkdir()
        (tmp_path / path_hash / "master.m3u8").write_text("#EXTM3U")

        service.clear_cache(file_path)

        assert not (tmp_path / path_hash).exists()

    def test_should_clear_all_cache_when_no_file(self, tmp_path: Path) -> None:
        service = HlsService(cache_dir=str(tmp_path))
        (tmp_path / "hash1").mkdir()
        (tmp_path / "hash2").mkdir()

        service.clear_cache()

        assert tmp_path.exists()  # Recreated
        assert list(tmp_path.iterdir()) == []

    def test_should_not_fail_when_cache_missing(self, tmp_path: Path) -> None:
        service = HlsService(cache_dir=str(tmp_path))
        # Should not raise
        service.clear_cache("/nonexistent.mkv")


@pytest.mark.unit
class TestHlsServiceValidateSource:
    """Tests for _validate_source."""

    def test_should_raise_when_file_missing(self, tmp_path: Path) -> None:
        missing = tmp_path / "missing.mkv"
        with pytest.raises(FileNotFoundError, match="Source file not found"):
            HlsService._validate_source(str(missing))

    def test_should_return_resolved_path(self, tmp_path: Path) -> None:
        source = tmp_path / "movie.mkv"
        source.write_text("fake")

        result = HlsService._validate_source(str(source))

        assert result == source.resolve()
