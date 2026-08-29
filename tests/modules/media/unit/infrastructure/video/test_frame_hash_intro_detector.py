"""Tests for FrameHashIntroDetector (the I/O composition layer).

Exercises the hashing pipeline — best-effort dropping of undecodable
episodes and the ``analyzed_count`` reported back — with the pure
correlation stubbed out (covered in ``test_frame_hash_correlator``).
"""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pytest

from src.modules.media.application.ports import DetectedIntro, EpisodeMediaRef
from src.modules.media.domain.value_objects import EpisodeId
from src.modules.media.infrastructure.video.frame_hash_correlator import FrameHashTuning
from src.modules.media.infrastructure.video.frame_hash_intro_detector import (
    FrameHashIntroDetector,
)

_TUNING = FrameHashTuning(analysis_window_seconds=300, frame_sample_fps=2.0)


def _hashes(n: int) -> np.ndarray:
    return np.arange(n, dtype=np.uint64)


def _make_hasher(*, returns: list[np.ndarray | None] | None = None) -> MagicMock:
    """Stub FrameHasher whose ``hash_episode`` yields arrays in order."""
    queue: list[np.ndarray | None] = list(returns) if returns is not None else []
    hasher = MagicMock()

    def hash_episode(_path: str, *, window_seconds: int, fps: float) -> np.ndarray | None:
        del window_seconds, fps
        return queue.pop(0) if queue else _hashes(10)

    hasher.hash_episode.side_effect = hash_episode
    return hasher


def _make_correlator(*, markers: dict | None = None) -> MagicMock:
    correlator = MagicMock()
    correlator.correlate.return_value = markers or {}
    return correlator


def _refs(count: int) -> list[EpisodeMediaRef]:
    return [
        EpisodeMediaRef(episode_id=EpisodeId.generate(), file_path=f"/series/s01e{i:02d}.mkv")
        for i in range(1, count + 1)
    ]


@pytest.mark.unit
class TestFrameHashIntroDetector:
    """Hashing-pipeline tests for FrameHashIntroDetector.detect."""

    def test_hashes_every_episode_and_reports_analyzed_count(self) -> None:
        correlator = _make_correlator()
        detector = FrameHashIntroDetector(
            frame_hasher=_make_hasher(),
            correlator=correlator,
        )

        result = detector.detect(_refs(3), _TUNING)

        passed = correlator.correlate.call_args.args[0]
        assert len(passed) == 3
        assert result.analyzed_count == 3

    def test_drops_episodes_that_fail_to_decode(self) -> None:
        correlator = _make_correlator()
        detector = FrameHashIntroDetector(
            frame_hasher=_make_hasher(returns=[_hashes(10), None, _hashes(10)]),
            correlator=correlator,
        )

        result = detector.detect(_refs(3), _TUNING)

        assert result.analyzed_count == 2

    def test_drops_episodes_with_empty_hashes(self) -> None:
        correlator = _make_correlator()
        detector = FrameHashIntroDetector(
            frame_hasher=_make_hasher(
                returns=[_hashes(10), np.empty(0, dtype=np.uint64), _hashes(10)]
            ),
            correlator=correlator,
        )

        result = detector.detect(_refs(3), _TUNING)

        assert result.analyzed_count == 2

    def test_unexpected_hasher_exception_drops_only_that_episode(self) -> None:
        correlator = _make_correlator()
        hasher = MagicMock()
        counter = {"n": 0}

        def hash_episode(_path: str, *, window_seconds: int, fps: float) -> np.ndarray | None:
            del window_seconds, fps
            counter["n"] += 1
            if counter["n"] == 1:
                raise RuntimeError("unexpected ffmpeg failure")
            return _hashes(10)

        hasher.hash_episode.side_effect = hash_episode
        detector = FrameHashIntroDetector(frame_hasher=hasher, correlator=correlator)

        result = detector.detect(_refs(3), _TUNING)

        assert result.analyzed_count == 2

    def test_passes_window_and_fps_to_the_hasher(self) -> None:
        hasher = _make_hasher()
        detector = FrameHashIntroDetector(frame_hasher=hasher, correlator=_make_correlator())

        detector.detect(
            _refs(2), FrameHashTuning(analysis_window_seconds=600, frame_sample_fps=3.0)
        )

        for call in hasher.hash_episode.call_args_list:
            assert call.kwargs["window_seconds"] == 600
            assert call.kwargs["fps"] == 3.0

    def test_returns_markers_from_the_correlator(self) -> None:
        ref = _refs(1)[0]
        marker = DetectedIntro(start_seconds=5.0, end_seconds=30.0, confidence=0.9)
        detector = FrameHashIntroDetector(
            frame_hasher=_make_hasher(),
            correlator=_make_correlator(markers={ref.episode_id: marker}),
        )

        result = detector.detect([ref], _TUNING)

        assert result.markers == {ref.episode_id: marker}

    def test_zero_analyzed_when_everything_fails(self) -> None:
        correlator = _make_correlator()
        detector = FrameHashIntroDetector(
            frame_hasher=_make_hasher(returns=[None, None]),
            correlator=correlator,
        )

        result = detector.detect(_refs(2), _TUNING)

        assert result.analyzed_count == 0
        assert correlator.correlate.call_args.args[0] == []


@pytest.mark.unit
class TestFrameHashIntroDetectorProgress:
    """The progress callback must fire once per episode, in order."""

    def test_reports_progress_for_every_episode(self) -> None:
        hasher = MagicMock()
        hasher.hash_episode.return_value = np.array([1, 2, 3], dtype=np.uint64)
        detector = FrameHashIntroDetector(frame_hasher=hasher)
        refs = [
            EpisodeMediaRef(episode_id=EpisodeId.generate(), file_path=f"/s01e{i:02d}.mkv")
            for i in (1, 2, 3)
        ]
        seen: list[tuple[int, int, EpisodeId]] = []

        detector.detect(refs, FrameHashTuning(), lambda *args: seen.append(args))

        assert [(done, total) for done, total, _ in seen] == [(1, 3), (2, 3), (3, 3)]
        assert [episode_id for _, _, episode_id in seen] == [r.episode_id for r in refs]

    def test_reports_progress_for_episodes_that_failed_to_hash(self) -> None:
        """A dropped episode still advances the counter.

        Otherwise progress would stall on an unreadable file and read as
        a wedged run.
        """
        hasher = MagicMock()
        hasher.hash_episode.side_effect = [None, np.array([1, 2], dtype=np.uint64)]
        detector = FrameHashIntroDetector(frame_hasher=hasher)
        refs = [
            EpisodeMediaRef(episode_id=EpisodeId.generate(), file_path=f"/s01e{i:02d}.mkv")
            for i in (1, 2)
        ]
        seen: list[int] = []

        detector.detect(refs, FrameHashTuning(), lambda done, _t, _e: seen.append(done))

        assert seen == [1, 2]

    def test_works_without_a_callback(self) -> None:
        hasher = MagicMock()
        hasher.hash_episode.return_value = np.array([1, 2, 3], dtype=np.uint64)
        detector = FrameHashIntroDetector(frame_hasher=hasher)
        refs = [EpisodeMediaRef(episode_id=EpisodeId.generate(), file_path="/s01e01.mkv")]

        result = detector.detect(refs, FrameHashTuning())

        assert result.analyzed_count == 1
