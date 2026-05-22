"""Tests for ThumbnailGenerationService.

The service wraps two subprocess calls (ffprobe to discover the source
duration, ffmpeg to render the sprite). Tests stub both via
``patch("...subprocess.run")`` so they exercise the real branching
without invoking real binaries. Every failure mode must degrade to
``None`` rather than raising — these tests pin that contract.
"""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from src.modules.media.infrastructure.streaming.thumbnail_service import (
    SPRITE_FILENAME,
    VTT_FILENAME,
    ThumbnailGenerationService,
)
from src.modules.settings.domain.value_objects import StreamingConfig

if TYPE_CHECKING:
    from pathlib import Path


def _fake_runtime_settings(*, ffmpeg_threads: int | None = None) -> MagicMock:
    runtime = MagicMock()
    runtime.streaming_snapshot_sync.return_value = StreamingConfig(
        ffmpeg_threads=ffmpeg_threads,
    )
    return runtime


_SUBPROCESS_TARGET = "src.modules.media.infrastructure.streaming.thumbnail_service.subprocess.run"
_WHICH_TARGET = "src.modules.media.infrastructure.streaming.thumbnail_service.shutil.which"


def _ffmpeg_writes_sprite(sprite_path: Path):
    """Side effect that emulates ffprobe + a successful ffmpeg sprite render."""

    def run(cmd, *_, **__):  # type: ignore[no-untyped-def]
        if cmd[0] == "ffprobe":
            return subprocess.CompletedProcess(cmd, 0, stdout="120.0\n", stderr="")
        sprite_path.parent.mkdir(parents=True, exist_ok=True)
        sprite_path.write_bytes(b"\xff\xd8\xff\xe0")  # JPEG SOI
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    return run


@pytest.mark.unit
class TestThumbnailGenerationService:
    def test_returns_paths_and_writes_sprite_plus_vtt_on_success(self, tmp_path: Path) -> None:
        output_dir = tmp_path / "thumbs"
        sprite_path = output_dir / SPRITE_FILENAME

        service = ThumbnailGenerationService(_fake_runtime_settings())
        with (
            patch(_WHICH_TARGET, return_value="/usr/bin/ffprobe"),
            patch(_SUBPROCESS_TARGET, side_effect=_ffmpeg_writes_sprite(sprite_path)),
        ):
            result = service.generate("/fake/movie.mkv", output_dir)

        assert result is not None
        assert result.sprite_path == sprite_path
        assert result.vtt_path == output_dir / VTT_FILENAME
        assert sprite_path.is_file()
        vtt_text = result.vtt_path.read_text(encoding="utf-8")
        assert vtt_text.startswith("WEBVTT")
        # 120s / 10s interval = 12 cues; last cue ends at 02:00.000.
        assert vtt_text.count("-->") == 12
        assert "00:01:50.000 --> 00:02:00.000" in vtt_text

    def test_returns_none_when_duration_is_zero(self, tmp_path: Path) -> None:
        output_dir = tmp_path / "thumbs"

        def run(cmd, *_, **__):  # type: ignore[no-untyped-def]
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        service = ThumbnailGenerationService(_fake_runtime_settings())
        with (
            patch(_WHICH_TARGET, return_value="/usr/bin/ffprobe"),
            patch(_SUBPROCESS_TARGET, side_effect=run) as mock_run,
        ):
            result = service.generate("/fake/movie.mkv", output_dir)

        assert result is None
        # Only ffprobe was called — short-circuit before touching ffmpeg.
        assert mock_run.call_count == 1
        assert not output_dir.exists()

    def test_returns_none_when_duration_below_interval(self, tmp_path: Path) -> None:
        output_dir = tmp_path / "thumbs"

        def run(cmd, *_, **__):  # type: ignore[no-untyped-def]
            return subprocess.CompletedProcess(cmd, 0, stdout="3.0\n", stderr="")

        service = ThumbnailGenerationService(_fake_runtime_settings())
        with (
            patch(_WHICH_TARGET, return_value="/usr/bin/ffprobe"),
            patch(_SUBPROCESS_TARGET, side_effect=run) as mock_run,
        ):
            result = service.generate("/fake/movie.mkv", output_dir)

        assert result is None
        assert mock_run.call_count == 1
        assert not output_dir.exists()

    def test_returns_none_when_ffmpeg_fails(self, tmp_path: Path) -> None:
        output_dir = tmp_path / "thumbs"

        def run(cmd, *_, **__):  # type: ignore[no-untyped-def]
            if cmd[0] == "ffprobe":
                return subprocess.CompletedProcess(cmd, 0, stdout="120.0\n", stderr="")
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="boom")

        service = ThumbnailGenerationService(_fake_runtime_settings())
        with (
            patch(_WHICH_TARGET, return_value="/usr/bin/ffprobe"),
            patch(_SUBPROCESS_TARGET, side_effect=run),
        ):
            result = service.generate("/fake/movie.mkv", output_dir)

        assert result is None
        assert not (output_dir / SPRITE_FILENAME).exists()
        assert not (output_dir / VTT_FILENAME).exists()

    def test_returns_none_when_ffmpeg_times_out(self, tmp_path: Path) -> None:
        output_dir = tmp_path / "thumbs"

        def run(cmd, *_, **__):  # type: ignore[no-untyped-def]
            if cmd[0] == "ffprobe":
                return subprocess.CompletedProcess(cmd, 0, stdout="120.0\n", stderr="")
            raise subprocess.TimeoutExpired(cmd, timeout=1)

        service = ThumbnailGenerationService(_fake_runtime_settings())
        with (
            patch(_WHICH_TARGET, return_value="/usr/bin/ffprobe"),
            patch(_SUBPROCESS_TARGET, side_effect=run),
        ):
            result = service.generate("/fake/movie.mkv", output_dir)

        assert result is None
        assert not (output_dir / SPRITE_FILENAME).exists()
        assert not (output_dir / VTT_FILENAME).exists()

    def test_returns_none_when_ffprobe_missing(self, tmp_path: Path) -> None:
        output_dir = tmp_path / "thumbs"

        service = ThumbnailGenerationService(_fake_runtime_settings())
        with patch(_WHICH_TARGET, return_value=None):
            result = service.generate("/fake/movie.mkv", output_dir)

        assert result is None

    def test_creates_nested_output_directory(self, tmp_path: Path) -> None:
        # The backfill job points the service at <media_dir>/.homeflix/thumbnails,
        # which typically does not exist. The service must create the full path.
        output_dir = tmp_path / "deeply" / "nested" / "thumbs"
        sprite_path = output_dir / SPRITE_FILENAME

        service = ThumbnailGenerationService(_fake_runtime_settings())
        with (
            patch(_WHICH_TARGET, return_value="/usr/bin/ffprobe"),
            patch(_SUBPROCESS_TARGET, side_effect=_ffmpeg_writes_sprite(sprite_path)),
        ):
            result = service.generate("/fake/movie.mkv", output_dir)

        assert result is not None
        assert sprite_path.is_file()
        assert (output_dir / VTT_FILENAME).is_file()

    def test_does_not_seek_into_source(self, tmp_path: Path) -> None:
        # Sprite covers source time 0..duration regardless of resume position;
        # the player maps ``video.currentTime`` directly into VTT cue times.
        output_dir = tmp_path / "thumbs"
        sprite_path = output_dir / SPRITE_FILENAME

        service = ThumbnailGenerationService(_fake_runtime_settings())
        with (
            patch(_WHICH_TARGET, return_value="/usr/bin/ffprobe"),
            patch(_SUBPROCESS_TARGET, side_effect=_ffmpeg_writes_sprite(sprite_path)) as mock_run,
        ):
            service.generate("/fake/movie.mkv", output_dir)

        ffmpeg_call = next(call for call in mock_run.call_args_list if call.args[0][0] == "ffmpeg")
        assert "-ss" not in ffmpeg_call.args[0]
