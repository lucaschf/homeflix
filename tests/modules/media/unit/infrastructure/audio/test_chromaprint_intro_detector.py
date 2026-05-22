"""Tests for ChromaprintIntroDetector.

The detector is an algorithm; tests build synthetic fingerprints
(deterministic intro prefixes + random tails) and assert the algorithm
recovers the planted intro within tolerance. No real fpcalc is
required.
"""

import random

import pytest

from src.modules.media.application.ports import (
    DetectedIntro,
    EpisodeFingerprint,
    IntroDetectorTuning,
)
from src.modules.media.domain.value_objects import EpisodeId
from src.modules.media.infrastructure.audio.chromaprint_intro_detector import (
    ChromaprintIntroDetector,
)

_DEFAULT_TUNING = IntroDetectorTuning()

_HASH_RATE = 8.0  # roughly the Chromaprint default; keeps math tidy
_BIT_MASK = 0xFFFFFFFF


def _make_random_hashes(count: int, *, seed: int) -> list[int]:
    """Return ``count`` deterministic 32-bit hashes."""
    rng = random.Random(seed)
    return [rng.randint(0, _BIT_MASK) for _ in range(count)]


def _flip_bits(value: int, count: int, *, seed: int) -> int:
    """Flip ``count`` random bits in a 32-bit integer for noise simulation."""
    rng = random.Random(seed)
    bit_positions = rng.sample(range(32), count)
    mask = 0
    for pos in bit_positions:
        mask |= 1 << pos
    return (value ^ mask) & _BIT_MASK


def _episode(
    *,
    intro_hashes: list[int],
    intro_offset_hashes: int,
    total_hashes: int,
    seed: int,
    noise_bits: int = 0,
    episode_id: EpisodeId | None = None,
) -> EpisodeFingerprint:
    """Build a fingerprint with ``intro_hashes`` planted at ``intro_offset_hashes``."""
    tail_hashes = _make_random_hashes(total_hashes, seed=seed)
    payload = list(tail_hashes)
    for i, intro_hash in enumerate(intro_hashes):
        position = intro_offset_hashes + i
        if position >= total_hashes:
            break
        if noise_bits > 0:
            payload[position] = _flip_bits(intro_hash, noise_bits, seed=seed * 1000 + i)
        else:
            payload[position] = intro_hash
    return EpisodeFingerprint(
        episode_id=episode_id or EpisodeId.generate(),
        hashes=payload,
        duration_seconds=total_hashes / _HASH_RATE,
    )


@pytest.fixture
def shared_intro() -> list[int]:
    """Deterministic intro segment shared across the synthetic episodes.

    ~80 hashes ≈ 10 seconds at 8 hashes/sec — comfortably above the
    default ``min_intro_seconds`` floor of 5.
    """
    return _make_random_hashes(80, seed=4242)


@pytest.mark.unit
class TestChromaprintIntroDetector:
    """Algorithm-level tests using synthetic fingerprints."""

    def test_returns_empty_when_fewer_than_two_fingerprints(self, shared_intro: list[int]) -> None:
        detector = ChromaprintIntroDetector()
        single = _episode(
            intro_hashes=shared_intro,
            intro_offset_hashes=0,
            total_hashes=400,
            seed=1,
        )

        assert detector.detect([single], _DEFAULT_TUNING) == {}

    def test_returns_empty_when_episodes_share_nothing(self) -> None:
        detector = ChromaprintIntroDetector()
        episodes = [
            EpisodeFingerprint(
                episode_id=EpisodeId.generate(),
                hashes=_make_random_hashes(400, seed=seed),
                duration_seconds=400 / _HASH_RATE,
            )
            for seed in range(3)
        ]

        result = detector.detect(episodes, _DEFAULT_TUNING)

        assert result == {}

    def test_detects_shared_intro_at_zero_offset(self, shared_intro: list[int]) -> None:
        detector = ChromaprintIntroDetector()
        episodes = [
            _episode(
                intro_hashes=shared_intro,
                intro_offset_hashes=0,
                total_hashes=400,
                seed=seed,
            )
            for seed in (1, 2, 3, 4)
        ]

        result = detector.detect(episodes, _DEFAULT_TUNING)

        assert len(result) == len(episodes)
        for episode in episodes:
            marker = result[episode.episode_id]
            assert isinstance(marker, DetectedIntro)
            # Intro starts at 0s, lasts ≈ 80/8 = 10s.
            assert marker.start_seconds == pytest.approx(0.0, abs=0.5)
            assert marker.end_seconds == pytest.approx(10.0, abs=1.5)
            assert marker.confidence == pytest.approx(1.0, abs=1e-6)

    def test_detects_intro_with_varying_cold_open_lengths(self, shared_intro: list[int]) -> None:
        detector = ChromaprintIntroDetector()
        # Each episode has a different cold-open length, so the intro
        # starts at a different offset in each fingerprint. The
        # detector must align them via shift search.
        offsets = [0, 16, 40, 24]  # in hashes — i.e. 0s, 2s, 5s, 3s of cold-open
        episodes = [
            _episode(
                intro_hashes=shared_intro,
                intro_offset_hashes=offset,
                total_hashes=500,
                seed=seed,
            )
            for seed, offset in enumerate(offsets, start=10)
        ]

        result = detector.detect(episodes, _DEFAULT_TUNING)

        assert len(result) == len(episodes)
        for episode, offset in zip(episodes, offsets, strict=True):
            marker = result[episode.episode_id]
            expected_start = offset / _HASH_RATE
            expected_end = (offset + len(shared_intro)) / _HASH_RATE
            assert marker.start_seconds == pytest.approx(expected_start, abs=1.0)
            assert marker.end_seconds == pytest.approx(expected_end, abs=1.5)

    def test_tolerates_mild_per_hash_bit_noise(self, shared_intro: list[int]) -> None:
        detector = ChromaprintIntroDetector()
        # Real Chromaprint output has 0-6 bits of jitter even on the
        # same source; flip 4 bits per intro hash and confirm the
        # detector still locks onto the segment.
        episodes = [
            _episode(
                intro_hashes=shared_intro,
                intro_offset_hashes=0,
                total_hashes=500,
                seed=seed,
                noise_bits=4,
            )
            for seed in (1, 2, 3)
        ]

        result = detector.detect(episodes, _DEFAULT_TUNING)

        assert len(result) == len(episodes)
        for episode in episodes:
            marker = result[episode.episode_id]
            assert marker.start_seconds == pytest.approx(0.0, abs=1.0)
            assert marker.end_seconds == pytest.approx(10.0, abs=1.5)

    def test_drops_episode_below_pair_agreement_threshold(self, shared_intro: list[int]) -> None:
        # Two episodes share the intro; the third has unique audio
        # throughout. The third must be omitted from the result, the
        # first two emitted with confidence < 1 (only one peer agreed).
        detector = ChromaprintIntroDetector(min_pair_agreement=0.5)
        with_intro = [
            _episode(
                intro_hashes=shared_intro,
                intro_offset_hashes=0,
                total_hashes=400,
                seed=seed,
            )
            for seed in (1, 2)
        ]
        outlier = EpisodeFingerprint(
            episode_id=EpisodeId.generate(),
            hashes=_make_random_hashes(400, seed=99),
            duration_seconds=400 / _HASH_RATE,
        )

        result = detector.detect([*with_intro, outlier], _DEFAULT_TUNING)

        assert outlier.episode_id not in result
        # 1 agreeing peer out of 2 possible → confidence == 0.5
        for episode in with_intro:
            assert result[episode.episode_id].confidence == pytest.approx(0.5, abs=0.01)

    def test_drops_short_matches_below_min_intro_seconds(self) -> None:
        # Plant a 3-second match — under the 5s default floor. The
        # detector should skip it entirely.
        short_intro = _make_random_hashes(int(3 * _HASH_RATE), seed=7)
        detector = ChromaprintIntroDetector()
        episodes = [
            _episode(
                intro_hashes=short_intro,
                intro_offset_hashes=0,
                total_hashes=400,
                seed=seed,
            )
            for seed in (1, 2, 3)
        ]

        assert detector.detect(episodes, _DEFAULT_TUNING) == {}

    def test_returns_empty_for_zero_duration_fingerprints(self) -> None:
        detector = ChromaprintIntroDetector()
        empty = [
            EpisodeFingerprint(
                episode_id=EpisodeId.generate(),
                hashes=[],
                duration_seconds=0.0,
            )
            for _ in range(3)
        ]

        assert detector.detect(empty, _DEFAULT_TUNING) == {}

    def test_confidence_is_capped_at_one(self, shared_intro: list[int]) -> None:
        detector = ChromaprintIntroDetector()
        episodes = [
            _episode(
                intro_hashes=shared_intro,
                intro_offset_hashes=0,
                total_hashes=400,
                seed=seed,
            )
            for seed in range(3)
        ]

        result = detector.detect(episodes, _DEFAULT_TUNING)

        for marker in result.values():
            assert 0.0 <= marker.confidence <= 1.0

    def test_max_intro_seconds_clamps_long_matches(self) -> None:
        # Plant a 60-hash (~7.5 s) shared region but configure the cap
        # at 5 s. The detector finds the full match, then truncates the
        # END so the persisted segment never goes past the cap.
        long_intro = _make_random_hashes(60, seed=99)
        detector = ChromaprintIntroDetector()
        episodes = [
            _episode(
                intro_hashes=long_intro,
                intro_offset_hashes=0,
                total_hashes=500,
                seed=seed,
            )
            for seed in (1, 2, 3)
        ]

        tuning = IntroDetectorTuning(max_intro_seconds=5.0)
        result = detector.detect(episodes, tuning)

        assert len(result) == len(episodes)
        for episode in episodes:
            marker = result[episode.episode_id]
            assert marker.start_seconds == pytest.approx(0.0, abs=0.5)
            # End clamped to start + max_intro_seconds (with a hair of
            # rounding slack for the float median).
            assert marker.end_seconds - marker.start_seconds <= 5.0 + 0.001

    def test_run_end_does_not_inflate_into_trailing_bad_streak(self) -> None:
        # Regression: the previous algorithm updated best_length on
        # every "still good" iteration without trimming, which let the
        # reported end include positions that hadn't yet exceeded
        # tolerance but already contained noisy hashes. The new
        # last_good tracking guarantees the end is always a confirmed
        # good hash.
        intro = _make_random_hashes(80, seed=42)
        detector = ChromaprintIntroDetector()
        episodes = [
            _episode(
                intro_hashes=intro,
                intro_offset_hashes=0,
                total_hashes=400,
                seed=seed,
            )
            for seed in (100, 200, 300)
        ]

        result = detector.detect(episodes, _DEFAULT_TUNING)

        for episode in episodes:
            marker = result[episode.episode_id]
            # 80 hashes / 8 hashes-per-second = 10 s. Allow at most a
            # half-second of slack for the float median; the previous
            # algorithm could overshoot by tolerance_hashes worth of
            # positions (~0.5 s on its own, much more in real episodes
            # where shared underscore extended the run).
            assert marker.end_seconds <= 10.5

    def test_misconfigured_alignment_window_does_not_disable_matching(
        self, shared_intro: list[int]
    ) -> None:
        # alignment_window_seconds * hash_rate < 1 would round down to
        # 0 without the floor in _pairwise_match, silently skipping
        # every shift. The detector must still fall back to a 1-hash
        # window so misconfiguration becomes "low quality matches" and
        # not "matching disabled".
        detector = ChromaprintIntroDetector(alignment_window_seconds=0.05)
        tuning = IntroDetectorTuning(min_intro_seconds=0.1)
        episodes = [
            _episode(
                intro_hashes=shared_intro,
                intro_offset_hashes=0,
                total_hashes=400,
                seed=seed,
            )
            for seed in range(3)
        ]

        result = detector.detect(episodes, tuning)

        # The 1-hash floor cannot detect a 10s intro, but we explicitly
        # do not require correctness here — just that the loop is not
        # short-circuited into producing an empty result for a sane
        # input pair. As long as the floor is in place, len(result)
        # should be 3 (some segment was identified for each episode).
        assert len(result) == len(episodes)
