"""Cross-correlate per-frame perceptual hashes to find a shared intro.

The pure matching algorithm for the frame-hash detector — it takes
already-computed per-frame dHashes (packed as ``uint64``) and returns
one marker per episode. Frame extraction + hashing lives in
:class:`FrameHasher`; :class:`FrameHashIntroDetector` composes the two
behind the :class:`IntroDetectorPort`.

Algorithm — diagonal voting (offset histogram)
----------------------------------------------

For every pair of episodes (A, B):

1. Build the Hamming-distance matrix between every frame of A and every
   frame of B (vectorised via a SWAR popcount over the XOR), then mark
   the cells whose distance is within ``hash_distance_threshold`` as
   matches.
2. Each diagonal ``d = (index_B - index_A)`` is a candidate alignment;
   unlike the audio detector this searches *every* offset in the
   window, so a long, variable-length cold open (teaser) that pushes
   the title sequence to a different second in each episode still
   aligns. The diagonal with the longest tolerant run of matches wins.
3. Project that run back into the seconds of A and B.

Each episode then accumulates one segment per peer it matched:

* ``confidence`` = fraction of peers that agreed.
* ``start`` / ``end`` = median across the peer contributions.

Episodes below ``min_pair_agreement`` or whose median segment is shorter
than ``min_intro_seconds`` are dropped.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

import numpy as np

from src.modules.media.application.ports.intro_detector_port import (
    DetectedIntro,
    IntroDetectorTuning,
)

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from src.modules.media.domain.value_objects import EpisodeId

_DEFAULT_MIN_PAIR_AGREEMENT = 0.5

# SWAR popcount constants for 64-bit lanes (kept as uint64 so numpy never
# promotes to Python ints mid-computation).
_M1 = np.uint64(0x5555555555555555)
_M2 = np.uint64(0x3333333333333333)
_M4 = np.uint64(0x0F0F0F0F0F0F0F0F)
_H01 = np.uint64(0x0101010101010101)
_SHIFT_1 = np.uint64(1)
_SHIFT_2 = np.uint64(2)
_SHIFT_4 = np.uint64(4)
_SHIFT_56 = np.uint64(56)


@dataclass(frozen=True)
class FrameHashTuning(IntroDetectorTuning):
    """Frame-hash calibration on top of the neutral bounds.

    Attributes:
        hash_distance_threshold: Per-frame Hamming-distance ceiling (out
            of 64 bits) two frames must be within to count as a match.
            Strict (8) — loosening it produces spurious matches on
            unrelated frames rather than recovering real intros.
        frame_sample_fps: Frames sampled per second; ties hash indices
            to seconds. Must match what :class:`FrameHasher` used.
        match_tolerance_frames: Consecutive non-matching frames a run
            absorbs before terminating.
        max_gap_seconds: Reserved for callers that merge nearby blocks;
            the consensus here uses the median segment directly.
    """

    hash_distance_threshold: int = 8
    frame_sample_fps: float = 2.0
    match_tolerance_frames: int = 2
    max_gap_seconds: float = 8.0


class FrameHashCorrelator:
    """Diagonal-voting cross-correlation over packed frame dHashes.

    Attributes:
        min_pair_agreement: Episodes whose match-rate against their
            peers falls below this fraction are dropped.
    """

    def __init__(self, *, min_pair_agreement: float = _DEFAULT_MIN_PAIR_AGREEMENT) -> None:
        self._min_pair_agreement = min_pair_agreement

    def correlate(
        self,
        episodes: Sequence[tuple[EpisodeId, np.ndarray]],
        tuning: FrameHashTuning,
    ) -> Mapping[EpisodeId, DetectedIntro]:
        """Run the full pairwise + voting pipeline. See module docstring."""
        usable = [(eid, h) for eid, h in episodes if h is not None and len(h) > 0]
        if len(usable) < 2:
            return {}

        per_episode_segments: dict[EpisodeId, list[tuple[float, float]]] = defaultdict(list)
        for i, (id_a, hashes_a) in enumerate(usable):
            for id_b, hashes_b in usable[i + 1 :]:
                match = self._pairwise_match(hashes_a, hashes_b, tuning)
                if match is None:
                    continue
                seg_a, seg_b = match
                per_episode_segments[id_a].append(seg_a)
                per_episode_segments[id_b].append(seg_b)

        return self._build_consensus(usable, per_episode_segments, tuning)

    def _pairwise_match(
        self,
        hashes_a: np.ndarray,
        hashes_b: np.ndarray,
        tuning: FrameHashTuning,
    ) -> tuple[tuple[float, float], tuple[float, float]] | None:
        """Best matching run between two frame-hash sequences, in seconds."""
        na = int(hashes_a.shape[0])
        nb = int(hashes_b.shape[0])
        if na == 0 or nb == 0:
            return None

        distances = _popcount64(hashes_a[:, None] ^ hashes_b[None, :])
        matches = distances <= tuning.hash_distance_threshold

        fps = tuning.frame_sample_fps
        min_run = max(1, int(tuning.min_intro_seconds * fps))
        best_len = 0
        best_start_a = 0
        best_offset = 0
        for offset in range(-(na - 1), nb):
            diagonal = matches.diagonal(offset=offset)
            # Cheap prune: a diagonal whose total matches can't beat the
            # current best can't host a longer run either — skip the
            # Python-level run scan.
            if int(diagonal.sum()) <= best_len:
                continue
            run_start, run_len = _longest_run(diagonal.tolist(), tuning.match_tolerance_frames)
            if run_len > best_len:
                best_len = run_len
                best_start_a = max(0, -offset) + run_start
                best_offset = offset

        if best_len < min_run:
            return None
        start_a = best_start_a / fps
        end_a = (best_start_a + best_len) / fps
        start_b = (best_start_a + best_offset) / fps
        end_b = (best_start_a + best_offset + best_len) / fps
        return (start_a, end_a), (start_b, end_b)

    def _build_consensus(
        self,
        episodes: Sequence[tuple[EpisodeId, np.ndarray]],
        per_episode_segments: Mapping[EpisodeId, list[tuple[float, float]]],
        tuning: FrameHashTuning,
    ) -> Mapping[EpisodeId, DetectedIntro]:
        """Aggregate per-pair matches into one marker per episode.

        Different peers may agree on different *portions* of the intro —
        a peer that only shares the title song (not the studio bumper
        before it) contributes a later-starting segment. Merging the
        per-pair segments (union of overlapping/adjacent ranges) and
        taking the largest block recovers the full intro, whereas a
        median of starts would clip it to whatever the middle peer saw.
        """
        result: dict[EpisodeId, DetectedIntro] = {}
        peer_count = len(episodes) - 1
        for episode_id, segments in per_episode_segments.items():
            if not segments:
                continue
            confidence = len(segments) / peer_count
            if confidence < self._min_pair_agreement:
                continue
            blocks = _merge_intervals(segments, tuning.max_gap_seconds)
            start_seconds, end_seconds = max(blocks, key=lambda block: block[1] - block[0])
            # Cap at max_intro_seconds — a run longer than that almost
            # always bled into shared post-title footage; truncating the
            # end beats dropping the marker.
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


def _merge_intervals(
    intervals: list[tuple[float, float]],
    max_gap_seconds: float,
) -> list[tuple[float, float]]:
    """Union overlapping/near intervals into merged blocks.

    Two intervals separated by ``max_gap_seconds`` or less are fused.
    Returns at least one block (input is never empty here).
    """
    ordered = sorted(intervals)
    merged: list[list[float]] = [list(ordered[0])]
    for start, end in ordered[1:]:
        if start - merged[-1][1] <= max_gap_seconds:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [(block[0], block[1]) for block in merged]


def _popcount64(values: np.ndarray) -> np.ndarray:
    """Per-element Hamming weight of a ``uint64`` array (SWAR)."""
    x = values
    x = x - ((x >> _SHIFT_1) & _M1)
    x = (x & _M2) + ((x >> _SHIFT_2) & _M2)
    x = (x + (x >> _SHIFT_4)) & _M4
    return cast("np.ndarray", (x * _H01) >> _SHIFT_56)


def _longest_run(matches: list[bool], tolerance: int) -> tuple[int, int]:
    """Return (start, length) of the longest tolerant run of matches.

    A run starts on a match and absorbs up to ``tolerance`` CONSECUTIVE
    misses before terminating; a fresh match resets the miss counter.
    The reported length always ends on a confirmed match (``last_good``)
    so a trailing miss streak never inflates the span — same guarantee
    as :class:`ChromaprintCorrelator`.
    """
    best_start = 0
    best_length = 0
    run_start = -1
    last_good = -1
    consecutive_bad = 0

    for i, ok in enumerate(matches):
        if run_start < 0:
            if not ok:
                continue
            run_start = i
            last_good = i
            consecutive_bad = 0
            if best_length < 1:
                best_start = run_start
                best_length = 1
            continue

        if not ok:
            consecutive_bad += 1
            if consecutive_bad > tolerance:
                run_start = -1
            continue

        consecutive_bad = 0
        last_good = i
        length = last_good - run_start + 1
        if length > best_length:
            best_start = run_start
            best_length = length

    return best_start, best_length


__all__ = ["FrameHashCorrelator", "FrameHashTuning"]
