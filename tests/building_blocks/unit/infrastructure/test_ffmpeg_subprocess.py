"""Tests for the shared ffmpeg subprocess helpers."""

import pytest

from src.building_blocks.infrastructure.ffmpeg_subprocess import (
    SUBPROCESS_TEXT_KWARGS,
    with_ffmpeg_threads,
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
class TestWithFfmpegThreads:
    """Tests for the ``-threads N`` injection helper."""

    def test_returns_input_unchanged_when_cap_is_none(self) -> None:
        # Identity (not just equality) so callers can wrap unconditionally
        # without paying for a list copy on the no-cap path.
        cmd = ["ffmpeg", "-i", "in.mkv", "out.m3u8"]
        assert with_ffmpeg_threads(cmd, None) is cmd

    def test_inserts_threads_flag_after_ffmpeg(self) -> None:
        result = with_ffmpeg_threads(["ffmpeg", "-i", "in.mkv", "out.m3u8"], 4)
        assert result == ["ffmpeg", "-threads", "4", "-i", "in.mkv", "out.m3u8"]

    def test_does_not_mutate_input_list(self) -> None:
        cmd = ["ffmpeg", "-i", "in.mkv"]
        with_ffmpeg_threads(cmd, 4)
        assert cmd == ["ffmpeg", "-i", "in.mkv"]

    def test_returns_input_unchanged_for_non_ffmpeg_command(self) -> None:
        # Defensive: if a caller ever passes an ffprobe (or anything else)
        # invocation through this helper, leave it alone instead of
        # silently injecting a flag that program does not recognize.
        cmd = ["ffprobe", "-show_entries", "format=duration", "in.mkv"]
        assert with_ffmpeg_threads(cmd, 4) is cmd

    def test_returns_input_unchanged_for_empty_list(self) -> None:
        cmd: list[str] = []
        assert with_ffmpeg_threads(cmd, 4) is cmd

    def test_recognises_absolute_path_to_ffmpeg(self) -> None:
        # Future refactors might use ``shutil.which("ffmpeg")`` (which
        # returns an absolute path) as ``argv[0]``. The helper must
        # still inject the cap or the silent no-op resurfaces.
        result = with_ffmpeg_threads(["/usr/bin/ffmpeg", "-i", "in.mkv"], 4)
        assert result == ["/usr/bin/ffmpeg", "-threads", "4", "-i", "in.mkv"]

    def test_recognises_windows_ffmpeg_exe(self) -> None:
        result = with_ffmpeg_threads(
            ["C:\\Program Files\\ffmpeg\\bin\\ffmpeg.exe", "-i", "in.mkv"],
            4,
        )
        assert result[0] == "C:\\Program Files\\ffmpeg\\bin\\ffmpeg.exe"
        assert result[1:3] == ["-threads", "4"]
