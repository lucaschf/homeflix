"""ffmpeg wrapper that turns an episode's leading frames into dHashes.

Samples the leading window of a video at a low frame rate, computes a
perceptual hash (dHash) per frame, and returns the hashes packed as
64-bit integers ready for cross-correlation. Frames are piped raw from
ffmpeg (no temp PNGs) for speed; the dHash is computed natively
(Pillow resize + horizontal diff — the exact operations
``imagehash.dhash`` performs) so no extra dependency is pulled and the
hashes match the calibrated spike bit-for-bit.

The wrapper is synchronous; async callers should use
``await asyncio.to_thread(hasher.hash_episode, ...)`` — same pattern as
``AudioExtractor``.
"""

from __future__ import annotations

import functools
import logging
import shutil
import subprocess
from typing import TYPE_CHECKING

import numpy as np
from PIL import Image

from src.modules.streaming.infrastructure.streaming._subprocess import with_ffmpeg_threads

if TYPE_CHECKING:
    from src.modules.media.application.ports.runtime_config_ports import StreamingConfigPort

_logger = logging.getLogger(__name__)

# Decoding the leading 10-min window of an episode is the slow step; a
# generous ceiling keeps a contended host or slow disk from being killed
# mid-decode while still bounding a genuinely stuck ffmpeg.
_DEFAULT_TIMEOUT_SECONDS = 300
# Frames are downscaled to this square before hashing. dHash resizes
# again to (hash_size + 1, hash_size) internally, so this only needs to
# be large enough to feed a clean downscale; 64px matches the calibrated
# spike. Decoding straight to this size keeps the raw pipe tiny.
_DEFAULT_SCALE_PX = 64
_DEFAULT_HASH_SIZE = 8  # dHash 8x8 → 64 bits, one uint64 per frame
_CHANNELS = 3  # rgb24


@functools.lru_cache(maxsize=1)
def _ffmpeg_path() -> str | None:
    """Return the resolved path to ffmpeg, or ``None`` if not on PATH.

    Cached so the lookup runs once per process and the missing-binary
    warning is logged at most once even across many episodes.
    """
    path = shutil.which("ffmpeg")
    if path is None:
        _logger.warning("ffmpeg not found — frame hashing disabled")
    return path


class FrameHasher:
    """Extract + perceptually hash an episode's leading frames.

    Attributes:
        timeout_seconds: Per-episode ffmpeg timeout. Defaults to 300s
            because decoding a 10-min window on a busy host can take a
            while; the value is a safety net, not a typical runtime.
        scale_px: Square size frames are decoded to before hashing.
        hash_size: dHash side length; ``hash_size**2`` bits per frame
            (8 → 64 bits → one uint64).
        runtime_settings: Snapshot facade for :class:`StreamingConfig`;
            ``ffmpeg_threads`` is read per call so admin edits take
            effect on the next tick.

    Example:
        >>> hasher = FrameHasher(runtime_settings=runtime_settings)
        >>> hashes = hasher.hash_episode(
        ...     "/series/show/s01e01.mkv", window_seconds=600, fps=2.0
        ... )
        >>> hashes.dtype
        dtype('uint64')
    """

    def __init__(
        self,
        runtime_settings: StreamingConfigPort,
        *,
        timeout_seconds: int = _DEFAULT_TIMEOUT_SECONDS,
        scale_px: int = _DEFAULT_SCALE_PX,
        hash_size: int = _DEFAULT_HASH_SIZE,
    ) -> None:
        self._runtime_settings = runtime_settings
        self._timeout = timeout_seconds
        self._scale_px = scale_px
        self._hash_size = hash_size

    def hash_episode(
        self,
        file_path: str,
        *,
        window_seconds: int,
        fps: float,
    ) -> np.ndarray | None:
        """Return one packed dHash per sampled frame, or ``None``.

        Args:
            file_path: Absolute path to the source media file.
            window_seconds: Length of the leading window to sample.
            fps: Frames sampled per second within the window. Frame
                index ``i`` corresponds to second ``i / fps``.

        Returns:
            A 1-D ``uint64`` array (one hash per frame, time-ordered),
            or ``None`` if ffmpeg is missing or the decode failed/empty.
        """
        ffmpeg = _ffmpeg_path()
        if ffmpeg is None:
            return None
        if window_seconds <= 0 or fps <= 0:
            _logger.error(
                "invalid sampling params for %s (window=%s, fps=%s)",
                file_path,
                window_seconds,
                fps,
            )
            return None

        raw = self._decode_frames(ffmpeg, file_path, window_seconds, fps)
        if not raw:
            return None
        return self._hash_raw_frames(raw, file_path)

    def _decode_frames(
        self,
        ffmpeg: str,
        file_path: str,
        window_seconds: int,
        fps: float,
    ) -> bytes | None:
        """Pipe the sampled window from ffmpeg as raw rgb24 bytes."""
        cmd = with_ffmpeg_threads(
            [
                ffmpeg,
                "-y",
                "-loglevel",
                "error",
                "-t",
                str(window_seconds),
                "-i",
                file_path,
                "-vf",
                f"fps={fps},scale={self._scale_px}:{self._scale_px}",
                "-pix_fmt",
                "rgb24",
                "-f",
                "rawvideo",
                "pipe:1",
            ],
            self._runtime_settings.streaming_snapshot_sync().ffmpeg_threads,
        )
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                check=False,
                timeout=self._timeout,
            )
        except subprocess.TimeoutExpired:
            _logger.warning("ffmpeg frame decode timed out for %s", file_path)
            return None
        except OSError:
            _logger.exception("ffmpeg frame decode crashed for %s", file_path)
            return None

        if result.returncode != 0:
            _logger.error(
                "ffmpeg frame decode failed for %s (exit=%d): %s",
                file_path,
                result.returncode,
                result.stderr.decode("utf-8", "replace").strip() if result.stderr else "",
            )
            return None
        return result.stdout

    def _hash_raw_frames(self, raw: bytes, file_path: str) -> np.ndarray | None:
        """Slice raw rgb24 bytes into frames and dHash each one."""
        frame_bytes = self._scale_px * self._scale_px * _CHANNELS
        frame_count = len(raw) // frame_bytes
        if frame_count == 0:
            _logger.error("ffmpeg produced no full frames for %s", file_path)
            return None

        frames = np.frombuffer(raw, dtype=np.uint8, count=frame_count * frame_bytes).reshape(
            frame_count, self._scale_px, self._scale_px, _CHANNELS
        )
        bit_width = self._hash_size * self._hash_size
        diffs = np.empty((frame_count, bit_width), dtype=bool)
        target = (self._hash_size + 1, self._hash_size)
        for i in range(frame_count):
            # Replicates imagehash.dhash exactly: greyscale, LANCZOS
            # downscale to (hash_size + 1, hash_size), then compare each
            # pixel to its right-hand neighbour, row-major.
            grey = Image.fromarray(frames[i]).convert("L").resize(target, Image.Resampling.LANCZOS)
            pixels = np.asarray(grey)
            diffs[i] = (pixels[:, 1:] > pixels[:, :-1]).flatten()

        # Pack the 64 bits of each frame into one uint64. Endianness is
        # irrelevant — Hamming distance over XOR is endianness-invariant
        # as long as every hash is packed the same way.
        return np.packbits(diffs, axis=1).view(np.uint64).reshape(-1)


__all__ = ["FrameHasher"]
