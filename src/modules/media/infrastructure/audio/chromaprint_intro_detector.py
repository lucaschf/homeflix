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
    IntroDetectorTuning,
)
from src.modules.media.domain.value_objects import EpisodeId

# Defaults tuned against synthetic fixtures and a couple of real
# anime / sitcom seasons. ``max_hash_hamming``, ``tolerance_hashes``,
# ``min_intro_seconds`` and ``max_intro_seconds`` are operator-tunable
# via :class:`IntroDetectorTuning` per ``detect()`` call (ADR-013);
# the other knobs are algorithm-internal and stay as constructor args.
_DEFAULT_MAX_ALIGNMENT_SHIFT_SECONDS = 30.0
_DEFAULT_MIN_PAIR_AGREEMENT = 0.5
_DEFAULT_ALIGNMENT_WINDOW_SECONDS = 60.0


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


class ChromaprintIntroDetector(IntroDetectorPort):
    """Cross-correlation detector backed by Chromaprint raw hashes.

    Attributes:
        max_alignment_shift_seconds: How far cold-open lengths between
            two episodes can differ. Wider values cost more search time;
            30s comfortably covers most production patterns.
        min_pair_agreement: Episodes whose match-rate against their
            peers falls below this fraction are dropped.
        alignment_window_seconds: How much of each fingerprint to scan
            when picking the alignment shift. Search is bounded so the
            algorithm stays linear in fingerprint length.

    Operator-tunable knobs (``max_hash_hamming``, ``tolerance_hashes``,
    ``min_intro_seconds``, ``max_intro_seconds``) are passed per
    ``detect()`` call via :class:`IntroDetectorTuning` so admin-panel
    edits take effect on the next tick.
    """

    def __init__(
        self,
        *,
        max_alignment_shift_seconds: float = _DEFAULT_MAX_ALIGNMENT_SHIFT_SECONDS,
        min_pair_agreement: float = _DEFAULT_MIN_PAIR_AGREEMENT,
        alignment_window_seconds: float = _DEFAULT_ALIGNMENT_WINDOW_SECONDS,
    ) -> None:
        self._max_alignment_shift_seconds = max_alignment_shift_seconds
        self._min_pair_agreement = min_pair_agreement
        self._alignment_window_seconds = alignment_window_seconds

    def detect(
        self,
        fingerprints: Sequence[EpisodeFingerprint],
        tuning: IntroDetectorTuning,
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
                match = self._pairwise_match(fp_a, fp_b, hash_rates, tuning)
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

        return self._build_consensus(usable, per_episode_segments, tuning)

    # ── pairwise matching ─────────────────────────────────────────────

    def _pairwise_match(
        self,
        fp_a: EpisodeFingerprint,
        fp_b: EpisodeFingerprint,
        hash_rates: Mapping[EpisodeId, float],
        tuning: IntroDetectorTuning,
    ) -> _PairwiseMatch | None:
        """Return the best matching range between two fingerprints, or ``None``."""
        a_hashes = fp_a.hashes
        b_hashes = fp_b.hashes

        rate = (hash_rates[fp_a.episode_id] + hash_rates[fp_b.episode_id]) / 2
        max_shift = max(1, int(self._max_alignment_shift_seconds * rate))
        # Floor at 1 so a misconfigured ``alignment_window_seconds`` (or
        # an unusually low hash rate) cannot collapse the scan window
        # to zero and silently disable matching for the pair.
        window_cap = max(1, int(self._alignment_window_seconds * rate))

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
            run_start, run_length = self._longest_run(distances, tuning)
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

    def _longest_run(
        self,
        distances: list[int],
        tuning: IntroDetectorTuning,
    ) -> tuple[int, int]:
        """Return (start, length) of the longest tolerant run.

        A "run" is a contiguous span starting on a good hash and
        absorbing up to ``tolerance_hashes`` CONSECUTIVE bad hashes
        before terminating. A fresh good hash resets the consecutive
        counter, so isolated noise inside an otherwise strong match
        is forgiven indefinitely.

        Crucially the reported segment always ends on a good hash —
        ``last_good`` tracks the rightmost good index inside the run
        and is the bound used when updating the best length, so a
        trailing bad streak never inflates the reported range. Without
        this, the previous implementation could overshoot the real end
        by up to ``tolerance_hashes`` chromaprint frames (a fraction
        of a second per frame, but noticeable on real episodes when
        the audio fades out into shared underscore music).
        """
        best_start = 0
        best_length = 0
        run_start = -1
        last_good = -1
        consecutive_bad = 0

        for i, d in enumerate(distances):
            is_bad = d > tuning.max_hash_hamming

            if run_start < 0:
                # Outside any run — only a good hash can start a new one.
                if is_bad:
                    continue
                run_start = i
                last_good = i
                consecutive_bad = 0
                if best_length < 1:
                    best_start = run_start
                    best_length = 1
                continue

            if is_bad:
                consecutive_bad += 1
                if consecutive_bad > tuning.tolerance_hashes:
                    run_start = -1
                continue

            # Good hash: reset the consecutive-bad counter and extend
            # the accepted region to here.
            consecutive_bad = 0
            last_good = i
            length = last_good - run_start + 1
            if length > best_length:
                best_start = run_start
                best_length = length

        return best_start, best_length

    # ── consensus voting ──────────────────────────────────────────────

    def _build_consensus(
        self,
        fingerprints: Sequence[EpisodeFingerprint],
        per_episode_segments: Mapping[EpisodeId, list[tuple[float, float]]],
        tuning: IntroDetectorTuning,
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
