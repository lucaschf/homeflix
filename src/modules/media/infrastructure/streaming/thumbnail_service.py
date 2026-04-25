"""FFmpeg-based scrub-preview thumbnail generation.

Owns the sprite + WebVTT rendering pipeline. Used by ``HlsService``
when preparing HLS streaming and by the periodic backfill job that
fills in thumbnails for media that has not been streamed yet.

Every failure mode (missing ffprobe, zero duration, ffmpeg non-zero
exit, timeout, write error) degrades to a ``None`` return rather than
raising — the player works fine without preview thumbnails and we
never want a sprite glitch to fail the calling pipeline.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.modules.media.application.streaming.thumbnail_vtt import (
    DEFAULT_INTERVAL_SECONDS,
    SpriteLayout,
    build_vtt,
    compute_layout,
)
from src.modules.media.infrastructure.streaming._subprocess import (
    SUBPROCESS_TEXT_KWARGS,
    with_ffmpeg_threads,
)

if TYPE_CHECKING:
    from pathlib import Path

_logger = logging.getLogger(__name__)

SPRITE_FILENAME = "sprite.jpg"
VTT_FILENAME = "sprite.vtt"

# JPEG quality for the sprite: ffmpeg -q:v where 2 is near-lossless and
# 31 is worst. 5 keeps previews sharp enough for hover without bloating
# the sprite — each 160x90 tile lands around 5-8KB on real content.
_THUMBNAIL_JPEG_QUALITY = 5
# Max seconds we give ffmpeg to finish the sprite. Thumbs are a nice-to-have;
# if ffmpeg is still running at this point we kill it and move on.
_THUMBNAIL_TIMEOUT = 300.0
_PROBE_TIMEOUT = 10


@dataclass(frozen=True)
class ThumbnailResult:
    """Output of a successful thumbnail-generation run.

    Attributes:
        sprite_path: Absolute path to the JPEG sprite on disk.
        vtt_path: Absolute path to the WebVTT cue file. This is the
            entry point a player loads — the VTT references the sprite
            tiles via media-fragment URLs.
        layout: Geometry that produced the sprite. Useful for logging
            and tests.
    """

    sprite_path: Path
    vtt_path: Path
    layout: SpriteLayout


class ThumbnailGenerationService:
    """Generate sprite + VTT scrub-preview thumbnails for a media file.

    Synchronous (subprocess-based). Callers that need to avoid blocking
    the event loop must dispatch the call themselves — typically via a
    daemon thread (HLS background generation) or ``asyncio.to_thread``
    (the periodic backfill job).

    Args:
        ffmpeg_threads: Maximum worker threads ffmpeg may use during
            sprite rendering. ``None`` keeps ffmpeg's default. Applied
            via ``-threads N`` on the render command.
    """

    def __init__(self, ffmpeg_threads: int | None = None) -> None:
        self._ffmpeg_threads = ffmpeg_threads

    def generate(
        self,
        file_path: str,
        output_dir: Path,
        *,
        interval_seconds: int = DEFAULT_INTERVAL_SECONDS,
    ) -> ThumbnailResult | None:
        """Produce ``sprite.jpg`` + ``sprite.vtt`` covering the full timeline.

        Args:
            file_path: Absolute path to the source video file.
            output_dir: Directory where the sprite and VTT files should
                be written. Created (with parents) if it does not exist.
            interval_seconds: Seconds between captured frames. Lower
                gives smoother scrub previews at the cost of a larger
                sprite.

        Returns:
            ``ThumbnailResult`` with the paths to the generated files,
            or ``None`` if the source duration could not be probed, the
            source was shorter than ``interval_seconds``, or any step
            of the ffmpeg/IO pipeline failed.
        """
        duration = self._probe_duration(file_path)
        if duration <= 0:
            _logger.debug("Thumbs skipped for %s: unknown duration", file_path)
            return None
        if duration < interval_seconds:
            _logger.debug(
                "Thumbs skipped for %s: duration %.1fs below interval",
                file_path,
                duration,
            )
            return None

        layout = compute_layout(duration, interval=interval_seconds)
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            _logger.exception("Failed creating thumbnail directory %s", output_dir)
            return None

        sprite_path = output_dir / SPRITE_FILENAME
        vtt_path = output_dir / VTT_FILENAME

        if not self._render_sprite(
            file_path, sprite_path, layout, interval_seconds, self._ffmpeg_threads
        ):
            return None

        try:
            vtt_path.write_text(
                build_vtt(SPRITE_FILENAME, layout, interval=interval_seconds),
                encoding="utf-8",
            )
        except OSError:
            _logger.exception("Failed writing thumbnail VTT for %s", file_path)
            return None

        _logger.info(
            "Thumbnails ready for %s: %d tiles (%dx%d grid)",
            file_path,
            layout.count,
            layout.columns,
            layout.rows,
        )
        return ThumbnailResult(sprite_path=sprite_path, vtt_path=vtt_path, layout=layout)

    @staticmethod
    def _render_sprite(
        file_path: str,
        sprite_path: Path,
        layout: SpriteLayout,
        interval_seconds: int,
        max_threads: int | None,
    ) -> bool:
        """Run ffmpeg to render the sprite JPEG. Returns ``False`` on any failure."""
        filter_expr = (
            f"fps=1/{interval_seconds},"
            f"scale={layout.tile_width}:{layout.tile_height}:force_original_aspect_ratio=decrease,"
            f"pad={layout.tile_width}:{layout.tile_height}:(ow-iw)/2:(oh-ih)/2,"
            f"tile={layout.columns}x{layout.rows}"
        )
        try:
            result = subprocess.run(
                with_ffmpeg_threads(
                    [
                        "ffmpeg",
                        "-i",
                        file_path,
                        "-vf",
                        filter_expr,
                        "-frames:v",
                        "1",
                        "-q:v",
                        str(_THUMBNAIL_JPEG_QUALITY),
                        "-an",
                        "-sn",
                        "-loglevel",
                        "error",
                        "-y",
                        str(sprite_path),
                    ],
                    max_threads,
                ),
                **SUBPROCESS_TEXT_KWARGS,
                check=False,
                timeout=_THUMBNAIL_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            _logger.warning("Thumbnail generation timed out for %s", file_path)
            return False
        except FileNotFoundError:
            _logger.warning("ffmpeg not available; skipping thumbnails for %s", file_path)
            return False

        if result.returncode != 0 or not sprite_path.is_file():
            _logger.warning(
                "Thumbnail ffmpeg failed for %s (code %s): %s",
                file_path,
                result.returncode,
                result.stderr.strip() if result.stderr else "",
            )
            return False
        return True

    @staticmethod
    def _probe_duration(file_path: str) -> float:
        """Return the source duration in seconds, or 0.0 on any failure."""
        if not shutil.which("ffprobe"):
            return 0.0
        try:
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    file_path,
                ],
                **SUBPROCESS_TEXT_KWARGS,
                check=False,
                timeout=_PROBE_TIMEOUT,
            )
        except (subprocess.TimeoutExpired, OSError):
            return 0.0
        try:
            return float(result.stdout.strip())
        except (TypeError, ValueError):
            return 0.0


__all__ = [
    "SPRITE_FILENAME",
    "VTT_FILENAME",
    "ThumbnailGenerationService",
    "ThumbnailResult",
]
