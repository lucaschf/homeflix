"""Tests for FrameHashCorrelator.

The correlator is the pure diagonal-voting algorithm; tests build
synthetic per-frame hashes (deterministic shared intro planted at
varying offsets + random tails) and assert it recovers the planted
intro within tolerance. No real ffmpeg/frames required.
"""

import numpy as np
import pytest

from src.modules.media.application.ports import DetectedIntro
from src.modules.media.domain.value_objects import EpisodeId
from src.modules.media.infrastructure.video.frame_hash_correlator import (
    FrameHashCorrelator,
    FrameHashTuning,
)

_FPS = 2.0
_DEFAULT_TUNING = FrameHashTuning(frame_sample_fps=_FPS)
_U64_MAX = np.iinfo(np.uint64).max


def _rand_hashes(count: int, *, seed: int) -> np.ndarray:
    """Return ``count`` deterministic random ``uint64`` frame hashes."""
    rng = np.random.default_rng(seed)
    return rng.integers(0, _U64_MAX, size=count, dtype=np.uint64)


def _flip_bits(value: np.uint64, count: int, *, seed: int) -> np.uint64:
    """Flip ``count`` random bits in a 64-bit hash (noise simulation)."""
    rng = np.random.default_rng(seed)
    mask = np.uint64(0)
    for bit in rng.choice(64, size=count, replace=False):
        mask |= np.uint64(1) << np.uint64(int(bit))
    return np.uint64(value ^ mask)


def _episode(
    *,
    intro: np.ndarray,
    offset: int,
    total: int,
    seed: int,
    noise_bits: int = 0,
) -> np.ndarray:
    """Build a hash sequence with ``intro`` planted at frame ``offset``."""
    arr = _rand_hashes(total, seed=seed).copy()
    end = min(total, offset + len(intro))
    segment = intro[: end - offset].copy()
    if noise_bits > 0:
        for i in range(len(segment)):
            segment[i] = _flip_bits(segment[i], noise_bits, seed=seed * 1000 + i)
    arr[offset:end] = segment
    return arr


@pytest.fixture
def shared_intro() -> np.ndarray:
    """80 frames ≈ 40s at 2 fps — comfortably above the 5s floor."""
    return _rand_hashes(80, seed=4242)


@pytest.mark.unit
class TestFrameHashCorrelator:
    """Algorithm-level tests using synthetic frame hashes."""

    def test_returns_empty_when_fewer_than_two(self, shared_intro: np.ndarray) -> None:
        correlator = FrameHashCorrelator()
        single = (EpisodeId.generate(), _episode(intro=shared_intro, offset=0, total=400, seed=1))

        assert correlator.correlate([single], _DEFAULT_TUNING) == {}

    def test_returns_empty_when_episodes_share_nothing(self) -> None:
        correlator = FrameHashCorrelator()
        episodes = [(EpisodeId.generate(), _rand_hashes(400, seed=seed)) for seed in range(3)]

        assert correlator.correlate(episodes, _DEFAULT_TUNING) == {}

    def test_detects_shared_intro_at_zero_offset(self, shared_intro: np.ndarray) -> None:
        correlator = FrameHashCorrelator()
        episodes = [
            (EpisodeId.generate(), _episode(intro=shared_intro, offset=0, total=400, seed=seed))
            for seed in (1, 2, 3, 4)
        ]

        result = correlator.correlate(episodes, _DEFAULT_TUNING)

        assert len(result) == len(episodes)
        for episode_id, _ in episodes:
            marker = result[episode_id]
            assert isinstance(marker, DetectedIntro)
            # 80 frames / 2 fps = 40s, starting at 0.
            assert marker.start_seconds == pytest.approx(0.0, abs=0.5)
            assert marker.end_seconds == pytest.approx(40.0, abs=1.0)
            assert marker.confidence == pytest.approx(1.0, abs=1e-6)

    def test_detects_intro_with_varying_cold_open_lengths(self, shared_intro: np.ndarray) -> None:
        correlator = FrameHashCorrelator()
        # Each episode's intro starts at a different offset — the whole
        # point of the full-offset diagonal search.
        offsets = [0, 40, 120, 200]  # frames → 0s, 20s, 60s, 100s of cold open
        episodes = [
            (
                EpisodeId.generate(),
                _episode(intro=shared_intro, offset=offset, total=600, seed=seed),
            )
            for seed, offset in enumerate(offsets, start=10)
        ]

        result = correlator.correlate(episodes, _DEFAULT_TUNING)

        assert len(result) == len(episodes)
        for (episode_id, _), offset in zip(episodes, offsets, strict=True):
            marker = result[episode_id]
            assert marker.start_seconds == pytest.approx(offset / _FPS, abs=1.0)
            assert marker.end_seconds == pytest.approx((offset + 80) / _FPS, abs=1.0)

    def test_tolerates_mild_per_frame_bit_noise(self, shared_intro: np.ndarray) -> None:
        correlator = FrameHashCorrelator()
        # 4 bits of jitter per frame stays within the default threshold 8.
        episodes = [
            (
                EpisodeId.generate(),
                _episode(intro=shared_intro, offset=0, total=500, seed=seed, noise_bits=4),
            )
            for seed in (1, 2, 3)
        ]

        result = correlator.correlate(episodes, _DEFAULT_TUNING)

        assert len(result) == len(episodes)
        for episode_id, _ in episodes:
            marker = result[episode_id]
            assert marker.start_seconds == pytest.approx(0.0, abs=1.0)
            assert marker.end_seconds == pytest.approx(40.0, abs=1.5)

    def test_drops_episode_below_pair_agreement(self, shared_intro: np.ndarray) -> None:
        correlator = FrameHashCorrelator(min_pair_agreement=0.5)
        with_intro = [
            (EpisodeId.generate(), _episode(intro=shared_intro, offset=0, total=400, seed=seed))
            for seed in (1, 2)
        ]
        outlier = (EpisodeId.generate(), _rand_hashes(400, seed=99))

        result = correlator.correlate([*with_intro, outlier], _DEFAULT_TUNING)

        assert outlier[0] not in result
        # 1 agreeing peer out of 2 possible → confidence 0.5.
        for episode_id, _ in with_intro:
            assert result[episode_id].confidence == pytest.approx(0.5, abs=0.01)

    def test_drops_short_matches_below_min_intro(self) -> None:
        # 6-frame (3s) shared region — under the 5s default floor.
        short_intro = _rand_hashes(6, seed=7)
        correlator = FrameHashCorrelator()
        episodes = [
            (EpisodeId.generate(), _episode(intro=short_intro, offset=0, total=400, seed=seed))
            for seed in (1, 2, 3)
        ]

        assert correlator.correlate(episodes, _DEFAULT_TUNING) == {}

    def test_max_intro_seconds_clamps_long_matches(self) -> None:
        long_intro = _rand_hashes(60, seed=99)  # 30s at 2 fps
        correlator = FrameHashCorrelator()
        episodes = [
            (EpisodeId.generate(), _episode(intro=long_intro, offset=0, total=500, seed=seed))
            for seed in (1, 2, 3)
        ]

        tuning = FrameHashTuning(frame_sample_fps=_FPS, max_intro_seconds=10.0)
        result = correlator.correlate(episodes, tuning)

        assert len(result) == len(episodes)
        for episode_id, _ in episodes:
            marker = result[episode_id]
            assert marker.end_seconds - marker.start_seconds <= 10.0 + 0.001

    def test_confidence_is_capped_at_one(self, shared_intro: np.ndarray) -> None:
        correlator = FrameHashCorrelator()
        episodes = [
            (EpisodeId.generate(), _episode(intro=shared_intro, offset=0, total=400, seed=seed))
            for seed in range(3)
        ]

        result = correlator.correlate(episodes, _DEFAULT_TUNING)

        for marker in result.values():
            assert 0.0 <= marker.confidence <= 1.0

    def test_ignores_empty_hash_arrays(self, shared_intro: np.ndarray) -> None:
        correlator = FrameHashCorrelator()
        episodes = [
            (EpisodeId.generate(), _episode(intro=shared_intro, offset=0, total=400, seed=1)),
            (EpisodeId.generate(), _episode(intro=shared_intro, offset=0, total=400, seed=2)),
            (EpisodeId.generate(), np.empty(0, dtype=np.uint64)),
        ]

        result = correlator.correlate(episodes, _DEFAULT_TUNING)

        # The empty episode is dropped; the other two still converge.
        assert len(result) == 2
