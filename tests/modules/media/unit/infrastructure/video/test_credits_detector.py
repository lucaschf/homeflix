"""Tests for CreditsDetector (combined edge + low-motion, latest-onset).

The pure scoring methods are exercised with synthetic gray frames; the
``detect`` composition is tested with the ffmpeg/ffprobe I/O stubbed, so
nothing here touches a real binary.
"""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from src.modules.media.application.ports.credits_detector_port import (
    CreditsDetectorTuning,
    CreditsSignal,
)
from src.modules.media.infrastructure.video import credits_detector as cd_mod
from src.modules.media.infrastructure.video.credits_detector import CreditsDetector

_H, _W = 180, 320
_TUNING = CreditsDetectorTuning(
    analysis_window_seconds=600, frame_sample_fps=1.0, min_credits_seconds=15
)


def _detector() -> CreditsDetector:
    runtime = SimpleNamespace(streaming_snapshot_sync=lambda: SimpleNamespace(ffmpeg_threads=None))
    return CreditsDetector(runtime)  # type: ignore[arg-type]


def _checker(n: int) -> np.ndarray:
    """``n`` high-edge frames (checkerboard) — strong text/edge signal."""
    board = (np.indices((_H, _W)).sum(axis=0) % 2 * 255).astype(np.uint8)
    return np.tile(board[None], (n, 1, 1))


def _flat(n: int, value: int = 100) -> np.ndarray:
    """``n`` low-texture, identical frames — low edge AND low motion."""
    return np.full((n, _H, _W), value, dtype=np.uint8)


def _noisy(n: int, *, seed: int) -> np.ndarray:
    """``n`` random frames — high motion, mid edge (acts as 'scene')."""
    rng = np.random.default_rng(seed)
    return rng.integers(0, 255, size=(n, _H, _W), dtype=np.uint8)


def _low_texture(n: int, *, seed: int) -> np.ndarray:
    """``n`` low-contrast frames — small but non-zero edge (a dim 'scene').

    Keeps the window's edge median above zero so the relative edge
    threshold is meaningful (a perfectly flat base medians to 0 and the
    detector — correctly — bails).
    """
    rng = np.random.default_rng(seed)
    return rng.integers(90, 110, size=(n, _H, _W), dtype=np.uint8)


@pytest.mark.unit
class TestCreditsDetectorSignals:
    """Pure per-signal scoring on synthetic frames."""

    def test_edge_candidate_fires_on_trailing_text_shelf(self) -> None:
        frames = np.concatenate([_low_texture(540, seed=1), _checker(60)])
        result = _detector()._edge_candidate(frames, _TUNING, window_start=0.0)
        assert result is not None
        assert result.signal is CreditsSignal.EDGE
        assert result.start_seconds == pytest.approx(540, abs=5)

    def test_motion_candidate_fires_on_trailing_static_run(self) -> None:
        frames = np.concatenate([_noisy(540, seed=2), _flat(60)])
        result = _detector()._motion_candidate(frames, _TUNING, window_start=0.0)
        assert result is not None
        assert result.signal is CreditsSignal.MOTION
        assert result.start_seconds == pytest.approx(540, abs=5)


@pytest.mark.unit
class TestCreditsDetectorDetect:
    """``detect`` composition with ffmpeg/ffprobe stubbed."""

    def _patch_io(
        self, monkeypatch: pytest.MonkeyPatch, detector: CreditsDetector, frames, duration
    ) -> None:
        monkeypatch.setattr(cd_mod, "_ffmpeg_path", lambda: "ffmpeg")
        monkeypatch.setattr(cd_mod, "_ffprobe_path", lambda: "ffprobe")
        monkeypatch.setattr(detector, "_file_duration", lambda _p: duration)
        monkeypatch.setattr(detector, "_decode_trailing", lambda _p, _t: frames)

    def test_picks_latest_onset_motion_over_earlier_edge(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Early high-edge block, then scene, then late static (low-motion).
        frames = np.concatenate([_checker(60), _noisy(180, seed=3), _flat(60)])
        detector = _detector()
        self._patch_io(monkeypatch, detector, frames, duration=300.0)

        result = detector.detect("/x.mkv", _TUNING)

        assert result is not None
        # Latest sustained region = the static tail → MOTION, near the end.
        assert result.signal is CreditsSignal.MOTION
        assert result.start_seconds == pytest.approx(240, abs=8)

    def test_returns_none_when_no_sustained_signal(self, monkeypatch: pytest.MonkeyPatch) -> None:
        detector = _detector()
        self._patch_io(monkeypatch, detector, _noisy(300, seed=4), duration=300.0)
        assert detector.detect("/x.mkv", _TUNING) is None

    def test_returns_none_when_duration_unprobeable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        detector = _detector()
        self._patch_io(monkeypatch, detector, _flat(60), duration=None)
        assert detector.detect("/x.mkv", _TUNING) is None

    def test_returns_none_when_ffmpeg_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(cd_mod, "_ffmpeg_path", lambda: None)
        monkeypatch.setattr(cd_mod, "_ffprobe_path", lambda: "ffprobe")
        assert _detector().detect("/x.mkv", _TUNING) is None
