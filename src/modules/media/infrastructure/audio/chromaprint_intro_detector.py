"""Cross-correlate Chromaprint fingerprints to find a season's shared intro.

Algorithm overview
------------------

For every pair of episodes (A, B):

1. **Find the best alignment shift.** Cold-opens vary in length, so the
   intro typically starts at different offsets in A and B. We sweep
   shift values ``s`` within ±``max_alignment_shift_seconds`` and, for
   each shift, compute the per-hash hamming distance series between
   the aligned portions of the two fingerprints.

2. **Find the longest matching segment for that shift.** Within the
   distance series we look for the longest contiguous run of
   low-distance positions. A small tolerance lets a few isolated bad
   hashes survive inside an otherwise strong run (chromaprint output
   is mildly noisy). The shift that produces the longest run wins.

3. Return the matched range projected back into A and B: that pair
   "agrees" on those time spans being the intro.

Each episode then accumulates votes from every pair it appears in:

* ``confidence`` = fraction of other episodes that agreed.
* ``start`` / ``end`` = median across the pair contributions.

Episodes whose confidence falls below ``min_pair_agreement`` or whose
median segment is shorter than ``min_intro_seconds`` are dropped — the
caller treats a missing entry as "no intro detected".
"""

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from statistics import median

from src.modules.media.application.ports.intro_detector_port import (
    DetectedIntro,
    EpisodeFingerprint,
    IntroDetectorPort,
)
from src.modules.media.domain.value_objects import EpisodeId

# Defaults tuned against synthetic fixtures and a couple of real
# anime / sitcom seasons. They are exposed as constructor kwargs so
# operators can adjust without forking the implementation.
_DEFAULT_MAX_ALIGNMENT_SHIFT_SECONDS = 30.0
_DEFAULT_MAX_HASH_HAMMING = 14  # bits, out of 32
_DEFAULT_TOLERANCE_HASHES = 4
_DEFAULT_MIN_INTRO_SECONDS = 5.0
_DEFAULT_MIN_PAIR_AGREEMENT = 0.5
_DEFAULT_ALIGNMENT_WINDOW_SECONDS = 60.0


@dataclass(frozen=True)
class _PairwiseMatch:
    """A range two fingerprints agree on."""

    start_a: int
    end_a: int  # exclusive
    start_b: int
    end_b: int  # exclusive
    avg_distance: float

    @property
    def length_hashes(self) -> int:
        """Length of the matched segment in hash positions."""
        return self.end_a - self.start_a


class ChromaprintIntroDetector(IntroDetectorPort):
    """Cross-correlation detector backed by Chromaprint raw hashes.

    Attributes:
        max_alignment_shift_seconds: How far cold-open lengths between
            two episodes can differ. Wider values cost more search time;
            30s comfortably covers most production patterns.
        max_hash_hamming: Per-hash hamming distance (out of 32 bits)
            considered "matching". 14 ≈ 44% bit divergence — generous
            enough to absorb the natural Chromaprint noise floor.
        tolerance_hashes: How many consecutive non-matching hashes a
            run can tolerate before terminating. Smooths over isolated
            spikes inside an otherwise strong match.
        min_intro_seconds: Discard matches shorter than this. Stops the
            detector from firing on incidental musical stings.
        min_pair_agreement: Episodes whose match-rate against their
            peers falls below this fraction are dropped.
        alignment_window_seconds: How much of each fingerprint to scan
            when picking the alignment shift. Search is bounded so the
            algorithm stays linear in fingerprint length.
    """

    def __init__(
        self,
        *,
        max_alignment_shift_seconds: float = _DEFAULT_MAX_ALIGNMENT_SHIFT_SECONDS,
        max_hash_hamming: int = _DEFAULT_MAX_HASH_HAMMING,
        tolerance_hashes: int = _DEFAULT_TOLERANCE_HASHES,
        min_intro_seconds: float = _DEFAULT_MIN_INTRO_SECONDS,
        min_pair_agreement: float = _DEFAULT_MIN_PAIR_AGREEMENT,
        alignment_window_seconds: float = _DEFAULT_ALIGNMENT_WINDOW_SECONDS,
    ) -> None:
        self._max_alignment_shift_seconds = max_alignment_shift_seconds
        self._max_hash_hamming = max_hash_hamming
        self._tolerance_hashes = tolerance_hashes
        self._min_intro_seconds = min_intro_seconds
        self._min_pair_agreement = min_pair_agreement
        self._alignment_window_seconds = alignment_window_seconds

    def detect(
        self, fingerprints: Sequence[EpisodeFingerprint]
    ) -> Mapping[EpisodeId, DetectedIntro]:
        """Run the full pairwise + voting pipeline.

        See module docstring for the algorithm.
        """
        if len(fingerprints) < 2:
            return {}

        # Per-episode hash rate — derived rather than hard-coded so the
        # detector survives chromaprint version changes.
        hash_rates = {fp.episode_id: _hash_rate(fp) for fp in fingerprints}
        # Fingerprints with too little audio to host a real intro fall
        # out of the pool entirely; otherwise they would confuse voting.
        usable = [fp for fp in fingerprints if hash_rates[fp.episode_id] > 0]
        if len(usable) < 2:
            return {}

        per_episode_segments: dict[EpisodeId, list[tuple[float, float]]] = defaultdict(list)

        for i, fp_a in enumerate(usable):
            for fp_b in usable[i + 1 :]:
                match = self._pairwise_match(fp_a, fp_b, hash_rates)
                if match is None:
                    continue
                rate_a = hash_rates[fp_a.episode_id]
                rate_b = hash_rates[fp_b.episode_id]
                per_episode_segments[fp_a.episode_id].append(
                    (match.start_a / rate_a, match.end_a / rate_a)
                )
                per_episode_segments[fp_b.episode_id].append(
                    (match.start_b / rate_b, match.end_b / rate_b)
                )

        return self._build_consensus(usable, per_episode_segments)

    # ── pairwise matching ─────────────────────────────────────────────

    def _pairwise_match(
        self,
        fp_a: EpisodeFingerprint,
        fp_b: EpisodeFingerprint,
        hash_rates: Mapping[EpisodeId, float],
    ) -> _PairwiseMatch | None:
        """Return the best matching range between two fingerprints, or ``None``."""
        a_hashes = fp_a.hashes
        b_hashes = fp_b.hashes

        rate = (hash_rates[fp_a.episode_id] + hash_rates[fp_b.episode_id]) / 2
        max_shift = max(1, int(self._max_alignment_shift_seconds * rate))
        window_cap = int(self._alignment_window_seconds * rate)

        best: _PairwiseMatch | None = None
        for shift in range(-max_shift, max_shift + 1):
            a_start = max(0, -shift)
            b_start = max(0, shift)
            scan_len = min(
                len(a_hashes) - a_start,
                len(b_hashes) - b_start,
                window_cap,
            )
            if scan_len <= 0:
                continue

            distances = [
                _popcount(a_hashes[a_start + k] ^ b_hashes[b_start + k]) for k in range(scan_len)
            ]
            run_start, run_length, avg = self._longest_run(distances)
            if run_length == 0:
                continue

            if best is None or run_length > best.length_hashes:
                best = _PairwiseMatch(
                    start_a=a_start + run_start,
                    end_a=a_start + run_start + run_length,
                    start_b=b_start + run_start,
                    end_b=b_start + run_start + run_length,
                    avg_distance=avg,
                )

        if best is None:
            return None
        # Reject the match if its projected duration falls below the
        # floor — the consensus step would drop it anyway, but doing it
        # here keeps the per-episode segment list cleaner.
        seconds = best.length_hashes / rate
        if seconds < self._min_intro_seconds:
            return None
        return best

    def _longest_run(self, distances: list[int]) -> tuple[int, int, float]:
        """Return (start, length, avg_distance) of the longest tolerant run.

        A "run" is a contiguous span of positions where the running
        count of "bad" hashes (distance > ``max_hash_hamming``) stays
        below ``tolerance_hashes``. The tolerance lets a few isolated
        outliers survive inside an otherwise strong match — chromaprint
        often emits one or two bit-flipped hashes per second of clean
        audio.
        """
        best_start = 0
        best_length = 0
        best_sum = 0
        run_start = 0
        run_bad = 0
        run_sum = 0
        run_length = 0
        for i, d in enumerate(distances):
            is_bad = d > self._max_hash_hamming
            if run_length == 0 and is_bad:
                continue
            if run_length == 0:
                run_start = i
                run_bad = 0
                run_sum = 0
            run_length = i - run_start + 1
            run_sum += d
            if is_bad:
                run_bad += 1
            if run_bad > self._tolerance_hashes:
                # End this run; record it if it beat the current best
                # without counting the trailing bad streak.
                trim = self._tolerance_hashes
                effective_length = run_length - trim
                if effective_length > best_length:
                    best_start = run_start
                    best_length = effective_length
                    best_sum = run_sum
                run_length = 0
                continue
            if run_length > best_length:
                best_start = run_start
                best_length = run_length
                best_sum = run_sum

        avg = (best_sum / best_length) if best_length else 0.0
        return best_start, best_length, avg

    # ── consensus voting ──────────────────────────────────────────────

    def _build_consensus(
        self,
        fingerprints: Sequence[EpisodeFingerprint],
        per_episode_segments: Mapping[EpisodeId, list[tuple[float, float]]],
    ) -> Mapping[EpisodeId, DetectedIntro]:
        """Aggregate per-pair matches into one marker per episode."""
        result: dict[EpisodeId, DetectedIntro] = {}
        peer_count = len(fingerprints) - 1
        for episode_id, segments in per_episode_segments.items():
            if not segments:
                continue
            confidence = len(segments) / peer_count
            if confidence < self._min_pair_agreement:
                continue
            start_seconds = float(median(s for s, _ in segments))
            end_seconds = float(median(e for _, e in segments))
            if end_seconds - start_seconds < self._min_intro_seconds:
                continue
            result[episode_id] = DetectedIntro(
                start_seconds=start_seconds,
                end_seconds=end_seconds,
                confidence=min(1.0, confidence),
            )
        return result


def _popcount(value: int) -> int:
    """Hamming weight of a 32-bit integer."""
    # Mask down to 32 bits in case a caller hands us a Python int that
    # overflowed the unsigned range — bit_count works on the absolute
    # value, but XOR'ing two large negatives could otherwise return a
    # surprising count.
    return (value & 0xFFFFFFFF).bit_count()


def _hash_rate(fp: EpisodeFingerprint) -> float:
    """Return hashes per second for ``fp``, or 0.0 when inapplicable."""
    if fp.duration_seconds <= 0 or not fp.hashes:
        return 0.0
    return len(fp.hashes) / fp.duration_seconds


__all__ = ["ChromaprintIntroDetector"]
