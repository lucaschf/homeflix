"""Per-file end-credits detector combining two complementary signals.

Credits onset is content-dependent, so no single heuristic covers every
title (validated across films, modern dark series, and old TV). This
detector samples the trailing window once and scores it with two signals,
returning the higher-confidence onset:

* **Edge / text density** — a sustained shelf of high edge density marks
  bright credits text (often scrolling) over a darker background. Works
  well for films.
* **Low motion** — a sustained valley of low frame-to-frame change marks
  static or slowly-changing credit cards. Works for modern episodic
  credits, including dark productions where edge/brightness fail.

Where neither signal produces a sustained region (e.g. credits rolling
over moving footage, as in much old TV) the detector returns ``None`` and
the title is recorded as ``NO_CREDITS_FOUND`` — a deliberate, honest
miss rather than a guess. The orchestrating job applies the operator's
``min_confidence`` before persisting.

Synchronous, like :class:`FrameHasher`; async callers should use
``await asyncio.to_thread(detector.detect, ...)``.
"""

from __future__ import annotations

import functools
import logging
import shutil
import subprocess
from typing import TYPE_CHECKING

import numpy as np

from src.modules.media.application.ports.credits_detector_port import (
    CreditsDetectorPort,
    CreditsDetectorTuning,
    CreditsSignal,
    DetectedCredits,
)
from src.modules.media.infrastructure.streaming._subprocess import (
    SUBPROCESS_TEXT_KWARGS,
    with_ffmpeg_threads,
)

if TYPE_CHECKING:
    from src.modules.media.application.ports.runtime_config_ports import StreamingConfigPort

_logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_SECONDS = 300
# Trailing window decoded to this size before scoring — large enough to
# resolve edge/motion structure, small enough to keep the raw pipe tiny.
_SCALE_W = 320
_SCALE_H = 180
# Frame-to-frame smoothing (frames) applied before run detection, so a
# single noisy frame doesn't fragment an otherwise sustained region.
_SMOOTH_FRAMES = 5
# Floor below which a candidate is treated as noise and dropped before
# the latest-onset selection. Low on purpose — it only rejects flat
# signals; real discrimination is by recency, not raw confidence.
_MIN_VIABLE_CONFIDENCE = 0.2


@functools.lru_cache(maxsize=1)
def _ffmpeg_path() -> str | None:
    path = shutil.which("ffmpeg")
    if path is None:
        _logger.warning("ffmpeg not found — credits detection disabled")
    return path


@functools.lru_cache(maxsize=1)
def _ffprobe_path() -> str | None:
    path = shutil.which("ffprobe")
    if path is None:
        _logger.warning("ffprobe not found — credits detection disabled")
    return path


def _smooth(values: np.ndarray, window: int) -> np.ndarray:
    """Centred moving average; returns the input unchanged when too short."""
    if window <= 1 or len(values) < window:
        return values
    kernel = np.ones(window) / window
    return np.convolve(values, kernel, mode="same")


class CreditsDetector(CreditsDetectorPort):
    """Combined edge + low-motion per-file credits-onset detector.

    Attributes:
        runtime_settings: Snapshot facade for :class:`StreamingConfig`;
            ``ffmpeg_threads`` is read per call so admin edits apply on
            the next tick.
        timeout_seconds: Per-file ffmpeg decode timeout (safety net).
    """

    def __init__(
        self,
        runtime_settings: StreamingConfigPort,
        *,
        timeout_seconds: int = _DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._runtime_settings = runtime_settings
        self._timeout = timeout_seconds

    def detect(self, file_path: str, tuning: CreditsDetectorTuning) -> DetectedCredits | None:
        """Detect the credits onset of ``file_path``. See module docstring."""
        if _ffmpeg_path() is None or _ffprobe_path() is None:
            return None

        duration = self._file_duration(file_path)
        if duration is None or duration <= 0:
            _logger.warning("could not probe duration for %s — skipping credits", file_path)
            return None

        frames = self._decode_trailing(file_path, tuning)
        if frames is None or frames.shape[0] < 2:
            return None

        window_start = max(0.0, duration - tuning.analysis_window_seconds)
        candidates = [
            self._edge_candidate(frames, tuning, window_start),
            self._motion_candidate(frames, tuning, window_start),
        ]
        viable = [c for c in candidates if c is not None and c.confidence >= _MIN_VIABLE_CONFIDENCE]
        if not viable:
            return None
        # Credits are the LAST sustained special region before the file
        # ends — so the latest onset, not the highest raw confidence,
        # identifies them. This is what lets a static-credits MOTION hit
        # win over a bright mid-episode scene that spikes EDGE to 1.0,
        # while still letting a film's scrolling-credits EDGE win when
        # it's the only (and latest) candidate.
        return max(viable, key=lambda c: c.start_seconds)

    # ── ffmpeg / ffprobe ──────────────────────────────────────────────

    def _file_duration(self, file_path: str) -> float | None:
        ffprobe = _ffprobe_path()
        if ffprobe is None:
            return None
        try:
            result = subprocess.run(
                [
                    ffprobe,
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "csv=p=0",
                    file_path,
                ],
                **SUBPROCESS_TEXT_KWARGS,
                check=False,
                timeout=self._timeout,
            )
        except (subprocess.TimeoutExpired, OSError):
            _logger.exception("ffprobe failed for %s", file_path)
            return None
        if result.returncode != 0:
            return None
        try:
            return float(result.stdout.strip())
        except (ValueError, AttributeError):
            return None

    def _decode_trailing(self, file_path: str, tuning: CreditsDetectorTuning) -> np.ndarray | None:
        """Pipe the trailing window from ffmpeg as raw gray frames."""
        ffmpeg = _ffmpeg_path()
        if ffmpeg is None:
            return None
        cmd = with_ffmpeg_threads(
            [
                ffmpeg,
                "-y",
                "-loglevel",
                "error",
                "-sseof",
                f"-{tuning.analysis_window_seconds}",
                "-i",
                file_path,
                "-vf",
                f"fps={tuning.frame_sample_fps},scale={_SCALE_W}:{_SCALE_H}",
                "-pix_fmt",
                "gray",
                "-f",
                "rawvideo",
                "pipe:1",
            ],
            self._runtime_settings.streaming_snapshot_sync().ffmpeg_threads,
        )
        try:
            result = subprocess.run(cmd, capture_output=True, check=False, timeout=self._timeout)
        except subprocess.TimeoutExpired:
            _logger.warning("ffmpeg credits decode timed out for %s", file_path)
            return None
        except OSError:
            _logger.exception("ffmpeg credits decode crashed for %s", file_path)
            return None
        if result.returncode != 0:
            _logger.error(
                "ffmpeg credits decode failed for %s (exit=%d): %s",
                file_path,
                result.returncode,
                result.stderr.decode("utf-8", "replace").strip() if result.stderr else "",
            )
            return None
        frame_bytes = _SCALE_W * _SCALE_H
        count = len(result.stdout) // frame_bytes
        if count == 0:
            return None
        return np.frombuffer(result.stdout, dtype=np.uint8, count=count * frame_bytes).reshape(
            count, _SCALE_H, _SCALE_W
        )

    # ── signals ───────────────────────────────────────────────────────

    def _edge_candidate(
        self, frames: np.ndarray, tuning: CreditsDetectorTuning, window_start: float
    ) -> DetectedCredits | None:
        """Longest sustained high edge-density run (bright/rolling credits)."""
        f = frames.astype(np.int16)
        gx = np.abs(f[:, :, 1:] - f[:, :, :-1]).mean(axis=(1, 2))
        gy = np.abs(f[:, 1:, :] - f[:, :-1, :]).mean(axis=(1, 2))
        edge = _smooth(gx + gy, _SMOOTH_FRAMES)
        median = float(np.median(edge))
        if median <= 0:
            return None
        threshold = median * tuning.edge_rel_factor
        run = _longest_run(edge >= threshold, tuning)
        if run is None:
            return None
        start_frame, end_frame = run
        region_mean = float(edge[start_frame:end_frame].mean())
        # Confidence: how far the shelf rises above the window median,
        # normalised so reaching ~2x median saturates to 1.0.
        confidence = float(np.clip((region_mean / median) - 1.0, 0.0, 1.0))
        start_seconds = window_start + start_frame / tuning.frame_sample_fps
        return DetectedCredits(
            start_seconds=start_seconds, confidence=confidence, signal=CreditsSignal.EDGE
        )

    def _motion_candidate(
        self, frames: np.ndarray, tuning: CreditsDetectorTuning, window_start: float
    ) -> DetectedCredits | None:
        """Longest sustained low frame-to-frame motion run (static credits)."""
        f = frames.astype(np.int16)
        motion = np.abs(np.diff(f, axis=0)).mean(axis=(1, 2))
        motion = _smooth(motion, _SMOOTH_FRAMES)
        median = float(np.median(motion))
        if median <= 0:
            return None
        threshold = median * tuning.motion_rel_factor
        run = _longest_run(motion <= threshold, tuning)
        if run is None:
            return None
        start_frame, end_frame = run
        region_mean = float(motion[start_frame:end_frame].mean())
        # Confidence: how deep the valley sits below the window median.
        confidence = float(np.clip(1.0 - (region_mean / median), 0.0, 1.0))
        # +1 frame: motion[i] is the change between frames i and i+1, so a
        # low-motion run starting at motion index k begins at frame k+1.
        start_seconds = window_start + (start_frame + 1) / tuning.frame_sample_fps
        return DetectedCredits(
            start_seconds=start_seconds, confidence=confidence, signal=CreditsSignal.MOTION
        )


def _longest_run(mask: np.ndarray, tuning: CreditsDetectorTuning) -> tuple[int, int] | None:
    """Return (start, end_excl) of the longest True run meeting the floor.

    ``mask`` flags qualifying frames (high edge / low motion). The longest
    contiguous run that meets ``min_credits_seconds`` wins; the caller
    computes the region mean from the original signal over ``[start, end)``.
    """
    min_run = max(1, int(tuning.min_credits_seconds * tuning.frame_sample_fps))
    best_start = -1
    best_end = -1
    best_len = 0
    run_start = -1
    for i, ok in enumerate(mask):
        if ok:
            if run_start < 0:
                run_start = i
            run_len = i - run_start + 1
            if run_len > best_len:
                best_len, best_start, best_end = run_len, run_start, i + 1
        else:
            run_start = -1
    if best_start < 0 or best_len < min_run:
        return None
    return best_start, best_end


__all__ = ["CreditsDetector"]
