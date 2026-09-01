"""Cross-correlate Chromaprint fingerprints to find a season's shared intro.

This module holds the *pure* correlation algorithm — it takes
already-computed fingerprints and returns one marker per episode. Audio
extraction and fpcalc invocation live in
:class:`ChromaprintIntroDetector`, which composes this correlator behind
the :class:`IntroDetectorPort`. Keeping the algorithm separate from the
I/O keeps it trivially unit-testable with synthetic fingerprints.

Algorithm overview
------------------

For every pair of episodes (A, B):

1. **Propose candidate alignments.** Intros do not start at the same
   second in every episode — a variable-length cold open can push the
   title sequence minutes apart across a season. Rather than sweeping
   every possible shift (quadratic in fingerprint length, hopeless on a
   20-minute analysis window), each hash is split into four 8-bit
   chunks and indexed by chunk position. A hash in B votes for the
   shift ``d = index_B - index_A`` of every A-hash it shares a chunk
   with, and the shifts with the most votes become the candidates.
   Chunking rather than whole-hash equality is what makes the vote
   survive the few bits of jitter Chromaprint emits for the same audio
   coming off two different encodes.

2. **Find the longest matching segment for each candidate.** Within the
   aligned distance series we look for the longest contiguous run of
   low-distance positions. A small tolerance lets a few isolated bad
   hashes survive inside an otherwise strong run (chromaprint output
   is mildly noisy). The candidate that produces the longest run wins.

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
from typing import cast

import numpy as np

from src.modules.media.application.ports.intro_detector_port import (
    DetectedIntro,
    IntroDetectorTuning,
)
from src.modules.media.domain.value_objects import EpisodeId

# Defaults tuned against synthetic fixtures and a couple of real
# anime / sitcom seasons. ``max_hash_hamming`` and ``tolerance_hashes``
# are operator-tunable via :class:`ChromaprintTuning` per ``correlate()``
# call (ADR-013); the other knobs are algorithm-internal and stay as
# constructor args.
_DEFAULT_MIN_PAIR_AGREEMENT = 0.5
_DEFAULT_CANDIDATE_OFFSETS = 8

# Each 32-bit hash is indexed as four 8-bit chunks. Two hashes of the
# same audio typically differ by a handful of bits; splitting into four
# chunks means such a pair still collides on whichever chunk the noise
# missed, which whole-hash equality would lose entirely.
_CHUNK_BITS = 8
_CHUNK_COUNT = 32 // _CHUNK_BITS
_CHUNK_KEYS = 1 << _CHUNK_BITS
# A candidate shift found by the vote is only approximate — refine the
# immediate neighbourhood too so an off-by-a-hash peak still lands on
# the true alignment.
_OFFSET_REFINE_RADIUS = 2
# Chunk values that repeat far more often than chance (long silences,
# tone beds) contribute noise, not signal, and their posting lists would
# dominate the vote's cost. Anything beyond this multiple of the
# expected bucket size is skipped — the audio-fingerprinting equivalent
# of dropping stop-words.
_MAX_POSTING_FACTOR = 8
_MIN_POSTING_CAP = 32

# SWAR popcount constants for 32-bit lanes (kept as uint32 so numpy
# never promotes to Python ints mid-computation).
_M1 = np.uint32(0x55555555)
_M2 = np.uint32(0x33333333)
_M4 = np.uint32(0x0F0F0F0F)
_H01 = np.uint32(0x01010101)
_SHIFT_1 = np.uint32(1)
_SHIFT_2 = np.uint32(2)
_SHIFT_4 = np.uint32(4)
_SHIFT_24 = np.uint32(24)


@dataclass(frozen=True)
class EpisodeFingerprint:
    """One episode's audio fingerprint, ready for cross-correlation.

    Attributes:
        episode_id: External id of the episode the fingerprint was
            computed for.
        hashes: Raw 32-bit Chromaprint fingerprint values, in the same
            order ``fpcalc`` emits them. The first hash corresponds to
            the start of the audio window analysed.
        duration_seconds: Length of audio that produced ``hashes``,
            as reported by fpcalc. Used to translate hash indices back
            to seconds without baking the Chromaprint hash rate into
            the correlator's contract.
    """

    episode_id: EpisodeId
    hashes: list[int]
    duration_seconds: float


@dataclass(frozen=True)
class ChromaprintTuning(IntroDetectorTuning):
    """Chromaprint-specific calibration on top of the neutral bounds.

    Attributes:
        max_hash_hamming: Per-hash Hamming-distance ceiling (out of 32
            bits) considered a "match".
        tolerance_hashes: How many consecutive non-matching hashes a
            run can absorb before terminating.
    """

    max_hash_hamming: int = 10
    tolerance_hashes: int = 2


@dataclass(frozen=True)
class _PairwiseMatch:
    """A range two fingerprints agree on."""

    start_a: int
    end_a: int  # exclusive
    start_b: int
    end_b: int  # exclusive

    @property
    def length_hashes(self) -> int:
        """Length of the matched segment in hash positions."""
        return self.end_a - self.start_a


@dataclass(frozen=True)
class _IndexedFingerprint:
    """A fingerprint prepared for pairwise correlation.

    Building the chunk index once per episode rather than once per pair
    matters: a season is quadratic in pairs, so the index would
    otherwise be rebuilt dozens of times per episode.

    Attributes:
        episode_id: Owning episode.
        hashes: The raw hashes as a ``uint32`` array.
        hash_rate: Hashes per second, derived from the fingerprint's
            own reported duration.
        buckets: One dict per chunk position, mapping a chunk value to
            the hash indices carrying it.
    """

    episode_id: EpisodeId
    hashes: np.ndarray
    hash_rate: float
    buckets: list[dict[int, np.ndarray]]

    @property
    def size(self) -> int:
        """Number of hashes in the fingerprint."""
        return int(self.hashes.shape[0])


class ChromaprintCorrelator:
    """Cross-correlation over Chromaprint raw hashes.

    Attributes:
        min_pair_agreement: Episodes whose match-rate against their
            peers falls below this fraction are dropped.
        candidate_offsets: How many top-voted alignments per pair are
            refined into a full run scan. More candidates cost linear
            extra time and only matter when the vote is ambiguous.

    Operator-tunable knobs (``max_hash_hamming``, ``tolerance_hashes``,
    ``min_intro_seconds``, ``max_intro_seconds``) are passed per
    ``correlate()`` call via :class:`ChromaprintTuning` so admin-panel
    edits take effect on the next tick.
    """

    def __init__(
        self,
        *,
        min_pair_agreement: float = _DEFAULT_MIN_PAIR_AGREEMENT,
        candidate_offsets: int = _DEFAULT_CANDIDATE_OFFSETS,
    ) -> None:
        self._min_pair_agreement = min_pair_agreement
        self._candidate_offsets = max(1, candidate_offsets)

    def correlate(
        self,
        fingerprints: Sequence[EpisodeFingerprint],
        tuning: ChromaprintTuning,
    ) -> Mapping[EpisodeId, DetectedIntro]:
        """Run the full pairwise + voting pipeline.

        See module docstring for the algorithm.
        """
        if len(fingerprints) < 2:
            return {}

        # Fingerprints with too little audio to host a real intro fall
        # out of the pool entirely; otherwise they would confuse voting.
        usable = [indexed for fp in fingerprints if (indexed := _index_fingerprint(fp)) is not None]
        if len(usable) < 2:
            return {}

        per_episode_segments: dict[EpisodeId, list[tuple[float, float]]] = defaultdict(list)

        for i, fp_a in enumerate(usable):
            for fp_b in usable[i + 1 :]:
                match = self._pairwise_match(fp_a, fp_b, tuning)
                if match is None:
                    continue
                per_episode_segments[fp_a.episode_id].append(
                    (match.start_a / fp_a.hash_rate, match.end_a / fp_a.hash_rate)
                )
                per_episode_segments[fp_b.episode_id].append(
                    (match.start_b / fp_b.hash_rate, match.end_b / fp_b.hash_rate)
                )

        return self._build_consensus(usable, per_episode_segments, tuning)

    # ── pairwise matching ─────────────────────────────────────────────

    def _pairwise_match(
        self,
        fp_a: _IndexedFingerprint,
        fp_b: _IndexedFingerprint,
        tuning: ChromaprintTuning,
    ) -> _PairwiseMatch | None:
        """Return the best matching range between two fingerprints, or ``None``."""
        rate = (fp_a.hash_rate + fp_b.hash_rate) / 2

        best: _PairwiseMatch | None = None
        for shift in self._candidate_shifts(fp_a, fp_b):
            a_start = max(0, -shift)
            b_start = max(0, shift)
            scan_len = min(fp_a.size - a_start, fp_b.size - b_start)
            if scan_len <= 0:
                continue

            distances = _popcount(
                fp_a.hashes[a_start : a_start + scan_len]
                ^ fp_b.hashes[b_start : b_start + scan_len]
            )
            run_start, run_length = _longest_run(
                distances <= tuning.max_hash_hamming, tuning.tolerance_hashes
            )
            if run_length == 0:
                continue

            if best is None or run_length > best.length_hashes:
                best = _PairwiseMatch(
                    start_a=a_start + run_start,
                    end_a=a_start + run_start + run_length,
                    start_b=b_start + run_start,
                    end_b=b_start + run_start + run_length,
                )

        if best is None:
            return None
        # Reject the match if its projected duration falls below the
        # floor — the consensus step would drop it anyway, but doing it
        # here keeps the per-episode segment list cleaner.
        seconds = best.length_hashes / rate
        if seconds < tuning.min_intro_seconds:
            return None
        return best

    def _candidate_shifts(
        self,
        fp_a: _IndexedFingerprint,
        fp_b: _IndexedFingerprint,
    ) -> list[int]:
        """Return the most promising alignments between two fingerprints.

        Votes every ``(chunk position, chunk value)`` collision into a
        histogram over ``index_B - index_A`` and keeps the highest
        peaks, each widened by :data:`_OFFSET_REFINE_RADIUS` so a peak
        that lands a hash or two off the true alignment still gets
        scanned.
        """
        votes = _offset_votes(fp_a, fp_b)
        if votes is None:
            return []

        take = min(self._candidate_offsets, int(votes.shape[0]))
        # argpartition gives the top-k without a full sort; only their
        # relative membership matters, not their order.
        peaks = np.argpartition(votes, -take)[-take:]
        origin = fp_a.size - 1
        shifts: set[int] = set()
        for peak in peaks.tolist():
            if votes[peak] == 0:
                continue
            for delta in range(-_OFFSET_REFINE_RADIUS, _OFFSET_REFINE_RADIUS + 1):
                shifts.add(peak - origin + delta)
        return sorted(shifts)

    # ── consensus voting ──────────────────────────────────────────────

    def _build_consensus(
        self,
        fingerprints: Sequence[_IndexedFingerprint],
        per_episode_segments: Mapping[EpisodeId, list[tuple[float, float]]],
        tuning: ChromaprintTuning,
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
            # Cap the segment at ``max_intro_seconds``. A real intro
            # virtually never exceeds two minutes — runs that come back
            # longer almost always include shared underscore /
            # transition music that bleeds past the title sequence.
            # Truncating the END is preferable to dropping the marker
            # entirely; the user gets a "Skip Intro" button covering
            # the shared region without overshooting deep into the
            # episode.
            if end_seconds - start_seconds > tuning.max_intro_seconds:
                end_seconds = start_seconds + tuning.max_intro_seconds
            if end_seconds - start_seconds < tuning.min_intro_seconds:
                continue
            result[episode_id] = DetectedIntro(
                start_seconds=start_seconds,
                end_seconds=end_seconds,
                confidence=min(1.0, confidence),
            )
        return result


def _index_fingerprint(fp: EpisodeFingerprint) -> _IndexedFingerprint | None:
    """Prepare ``fp`` for correlation, or ``None`` when it is unusable.

    A fingerprint with no hashes or no reported duration cannot be
    mapped back to seconds, so it is dropped rather than allowed to
    skew the consensus.
    """
    rate = _hash_rate(fp)
    if rate <= 0:
        return None
    # Mask to 32 bits before the unsigned cast: fpcalc emits signed
    # values in some packagings, and Hamming distance must be taken over
    # the same bit pattern either way.
    hashes = (np.asarray(fp.hashes, dtype=np.int64) & 0xFFFFFFFF).astype(np.uint32)
    return _IndexedFingerprint(
        episode_id=fp.episode_id,
        hashes=hashes,
        hash_rate=rate,
        buckets=[_chunk_buckets(hashes, chunk) for chunk in range(_CHUNK_COUNT)],
    )


def _chunk_buckets(hashes: np.ndarray, chunk: int) -> dict[int, np.ndarray]:
    """Group hash indices by the value of their ``chunk``-th byte.

    Over-represented values are dropped (see
    :data:`_MAX_POSTING_FACTOR`): they carry no alignment information
    and would otherwise dominate the vote's cost.
    """
    keys = (hashes >> np.uint32(chunk * _CHUNK_BITS)) & np.uint32(_CHUNK_KEYS - 1)
    order = np.argsort(keys, kind="stable")
    ordered_keys = keys[order]
    starts = np.concatenate(([0], np.flatnonzero(np.diff(ordered_keys)) + 1))
    groups = np.split(order, starts[1:])
    cap = max(_MIN_POSTING_CAP, _MAX_POSTING_FACTOR * hashes.shape[0] // _CHUNK_KEYS)
    return {
        int(ordered_keys[start]): group
        for start, group in zip(starts.tolist(), groups, strict=True)
        if group.shape[0] <= cap
    }


def _offset_votes(fp_a: _IndexedFingerprint, fp_b: _IndexedFingerprint) -> np.ndarray | None:
    """Histogram of ``index_B - index_A`` over every chunk collision.

    Returns ``None`` when the two fingerprints share no chunk at all.
    The histogram is indexed by ``shift + len(A) - 1`` so shifts that
    place B before A stay addressable.
    """
    collisions: list[np.ndarray] = []
    for chunk in range(_CHUNK_COUNT):
        a_buckets = fp_a.buckets[chunk]
        for key, b_indices in fp_b.buckets[chunk].items():
            a_indices = a_buckets.get(key)
            if a_indices is None:
                continue
            collisions.append((b_indices[:, None] - a_indices[None, :]).ravel())

    if not collisions:
        return None
    shifts = np.concatenate(collisions) + (fp_a.size - 1)
    return np.bincount(shifts, minlength=fp_a.size + fp_b.size - 1)


def _popcount(values: np.ndarray) -> np.ndarray:
    """Per-element Hamming weight of a ``uint32`` array (SWAR)."""
    x = values
    x = x - ((x >> _SHIFT_1) & _M1)
    x = (x & _M2) + ((x >> _SHIFT_2) & _M2)
    x = (x + (x >> _SHIFT_4)) & _M4
    return cast("np.ndarray", (x * _H01) >> _SHIFT_24)


def _longest_run(matches: np.ndarray, tolerance: int) -> tuple[int, int]:
    """Return (start, length) of the longest tolerant run of matches.

    A "run" is a contiguous span starting on a good hash and absorbing
    up to ``tolerance`` CONSECUTIVE bad hashes before terminating. A
    fresh good hash resets the consecutive counter, so isolated noise
    inside an otherwise strong match is forgiven indefinitely.

    Equivalently — and this is how it is computed — the matching
    positions are grouped wherever two consecutive ones sit more than
    ``tolerance + 1`` apart, and the widest group wins. Because the
    span is measured between the first and last MATCH of a group, the
    reported segment always ends on a good hash: a trailing bad streak
    can never inflate the range.
    """
    positions = np.flatnonzero(matches)
    if positions.shape[0] == 0:
        return 0, 0
    breaks = np.flatnonzero(np.diff(positions) > tolerance + 1)
    group_starts = np.concatenate(([0], breaks + 1))
    group_ends = np.concatenate((breaks, [positions.shape[0] - 1]))
    lengths = positions[group_ends] - positions[group_starts] + 1
    widest = int(np.argmax(lengths))
    return int(positions[group_starts[widest]]), int(lengths[widest])


def _hash_rate(fp: EpisodeFingerprint) -> float:
    """Return hashes per second for ``fp``, or 0.0 when inapplicable."""
    if fp.duration_seconds <= 0 or not fp.hashes:
        return 0.0
    return len(fp.hashes) / fp.duration_seconds


__all__ = ["ChromaprintCorrelator", "ChromaprintTuning", "EpisodeFingerprint"]
