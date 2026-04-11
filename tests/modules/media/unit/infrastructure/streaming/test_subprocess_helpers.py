"""Tests for streaming subprocess helpers and HLS utility functions."""

import pytest

from src.modules.media.infrastructure.streaming._subprocess import SUBPROCESS_TEXT_KWARGS
from src.modules.media.infrastructure.streaming.hls_service import (
    media_type_for,
    rewrite_m3u8,
)


@pytest.mark.unit
class TestSubprocessTextKwargs:
    """Tests for the shared SUBPROCESS_TEXT_KWARGS mapping."""

    def test_should_capture_output(self) -> None:
        assert SUBPROCESS_TEXT_KWARGS["capture_output"] is True

    def test_should_use_text_mode(self) -> None:
        assert SUBPROCESS_TEXT_KWARGS["text"] is True

    def test_should_use_utf8_encoding(self) -> None:
        assert SUBPROCESS_TEXT_KWARGS["encoding"] == "utf-8"

    def test_should_replace_decoding_errors(self) -> None:
        assert SUBPROCESS_TEXT_KWARGS["errors"] == "replace"

    def test_should_be_immutable(self) -> None:
        with pytest.raises(TypeError):
            SUBPROCESS_TEXT_KWARGS["capture_output"] = False  # type: ignore[index]


@pytest.mark.unit
class TestMediaTypeFor:
    """Tests for media_type_for content-type detection."""

    def test_should_return_hls_playlist_type_for_m3u8(self) -> None:
        assert media_type_for("playlist.m3u8") == "application/vnd.apple.mpegurl"

    def test_should_return_video_mp2t_for_ts(self) -> None:
        assert media_type_for("segment_0001.ts") == "video/mp2t"

    def test_should_return_text_vtt_for_vtt(self) -> None:
        assert media_type_for("subtitle.vtt") == "text/vtt"

    def test_should_handle_uppercase_extension(self) -> None:
        assert media_type_for("PLAYLIST.M3U8") == "application/vnd.apple.mpegurl"

    def test_should_return_octet_stream_for_unknown(self) -> None:
        assert media_type_for("file.xyz") == "application/octet-stream"

    def test_should_handle_path_with_directory(self) -> None:
        assert media_type_for("/cache/abc/video/segment.ts") == "video/mp2t"


@pytest.mark.unit
class TestRewriteM3u8:
    """Tests for rewriting relative references in M3U8 playlists."""

    def test_should_prefix_relative_segment_references(self) -> None:
        playlist = "#EXTM3U\n#EXTINF:10,\nsegment_0000.ts\n"

        result = rewrite_m3u8(playlist, "https://example.com/hls/abc")

        assert "https://example.com/hls/abc/segment_0000.ts" in result

    def test_should_prefix_uri_attributes(self) -> None:
        playlist = '#EXT-X-MEDIA:TYPE=AUDIO,URI="audio_1/playlist.m3u8"\n'

        result = rewrite_m3u8(playlist, "https://example.com/hls/abc")

        assert 'URI="https://example.com/hls/abc/audio_1/playlist.m3u8"' in result

    def test_should_preserve_comment_lines(self) -> None:
        playlist = "#EXTM3U\n#EXT-X-VERSION:3\n#EXTINF:10,\nsegment.ts\n"

        result = rewrite_m3u8(playlist, "https://example.com/x")

        assert "#EXTM3U" in result
        assert "#EXT-X-VERSION:3" in result

    def test_should_not_rewrite_absolute_urls(self) -> None:
        playlist = "#EXTM3U\nhttps://other.com/segment.ts\n"

        result = rewrite_m3u8(playlist, "https://example.com/x")

        assert "https://other.com/segment.ts" in result
        assert "https://example.com/x/https://other.com/segment.ts" not in result

    def test_should_not_rewrite_root_relative_paths(self) -> None:
        playlist = "#EXTM3U\n/some/path/segment.ts\n"

        result = rewrite_m3u8(playlist, "https://example.com/x")

        assert "/some/path/segment.ts" in result
        assert "https://example.com/x//some/path/segment.ts" not in result

    def test_should_not_rewrite_absolute_uri_attributes(self) -> None:
        playlist = '#EXT-X-MEDIA:URI="https://other.com/playlist.m3u8"\n'

        result = rewrite_m3u8(playlist, "https://example.com/x")

        assert 'URI="https://other.com/playlist.m3u8"' in result
