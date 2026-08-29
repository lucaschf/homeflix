"""Tests for ChromaprintIntroDetector (the I/O composition layer).

These exercise the extraction pipeline — ffmpeg + fpcalc per episode,
best-effort dropping of unreadable media, and the ``analyzed_count``
reported back — with the pure cross-correlation stubbed out (it has its
own tests in ``test_chromaprint_correlator``).
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest

from src.modules.media.application.ports import DetectedIntro, EpisodeMediaRef
from src.modules.media.domain.value_objects import EpisodeId
from src.modules.media.infrastructure.audio.chromaprint_correlator import (
    ChromaprintTuning,
    EpisodeFingerprint,
)
from src.modules.media.infrastructure.audio.chromaprint_intro_detector import (
    ChromaprintIntroDetector,
)
from src.modules.media.infrastructure.audio.chromaprint_service import ChromaprintFingerprint

if TYPE_CHECKING:
    from collections.abc import Iterator

_TUNING = ChromaprintTuning(analysis_window_seconds=120)


def _make_audio_extractor(*, returns: list[Path | None] | None = None) -> MagicMock:
    """Stub AudioExtractor whose ``extract_temporary`` yields paths in order."""
    queue: list[Path | None] = list(returns) if returns is not None else []
    extractor = MagicMock()

    @contextmanager
    def extract_temporary(_file_path: str, *, duration_seconds: int) -> Iterator[Path | None]:
        del duration_seconds
        yield queue.pop(0) if queue else Path("/tmp/fake.wav")

    extractor.extract_temporary.side_effect = extract_temporary
    return extractor


def _make_chromaprint(*, returns: list[ChromaprintFingerprint | None] | None = None) -> MagicMock:
    queue: list[ChromaprintFingerprint | None] = list(returns) if returns is not None else []
    service = MagicMock()

    def fingerprint(_path: object) -> ChromaprintFingerprint | None:
        if queue:
            return queue.pop(0)
        return ChromaprintFingerprint(duration_seconds=120.0, hashes=[1, 2, 3])

    service.fingerprint.side_effect = fingerprint
    return service


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
class TestChromaprintIntroDetector:
    """Extraction-pipeline tests for ChromaprintIntroDetector.detect."""

    def test_fingerprints_every_episode_and_reports_analyzed_count(self) -> None:
        correlator = _make_correlator()
        detector = ChromaprintIntroDetector(
            audio_extractor=_make_audio_extractor(),
            chromaprint_service=_make_chromaprint(),
            correlator=correlator,
        )

        refs = _refs(3)
        result = detector.detect(refs, _TUNING)

        # All three produced a fingerprint → all three handed to the
        # correlator and counted as analysed.
        passed = correlator.correlate.call_args.args[0]
        assert len(passed) == 3
        assert all(isinstance(fp, EpisodeFingerprint) for fp in passed)
        assert result.analyzed_count == 3

    def test_drops_episodes_whose_audio_extraction_fails(self) -> None:
        correlator = _make_correlator()
        # Middle episode's extraction yields None.
        detector = ChromaprintIntroDetector(
            audio_extractor=_make_audio_extractor(
                returns=[Path("/tmp/a.wav"), None, Path("/tmp/c.wav")]
            ),
            chromaprint_service=_make_chromaprint(),
            correlator=correlator,
        )

        result = detector.detect(_refs(3), _TUNING)

        assert len(correlator.correlate.call_args.args[0]) == 2
        assert result.analyzed_count == 2

    def test_drops_episodes_whose_fingerprint_fails(self) -> None:
        correlator = _make_correlator()
        detector = ChromaprintIntroDetector(
            audio_extractor=_make_audio_extractor(),
            chromaprint_service=_make_chromaprint(
                returns=[
                    ChromaprintFingerprint(duration_seconds=120.0, hashes=[1, 2, 3]),
                    None,
                    ChromaprintFingerprint(duration_seconds=120.0, hashes=[4, 5, 6]),
                ]
            ),
            correlator=correlator,
        )

        result = detector.detect(_refs(3), _TUNING)

        assert result.analyzed_count == 2

    def test_unexpected_extractor_exception_drops_only_that_episode(self) -> None:
        correlator = _make_correlator()
        crashing = MagicMock()
        counter = {"n": 0}

        @contextmanager
        def extract_temporary(_file_path: str, *, duration_seconds: int) -> Iterator[Path | None]:
            del duration_seconds
            counter["n"] += 1
            if counter["n"] == 1:
                raise RuntimeError("unexpected ffmpeg failure")
            yield Path("/tmp/fake.wav")

        crashing.extract_temporary.side_effect = extract_temporary

        detector = ChromaprintIntroDetector(
            audio_extractor=crashing,
            chromaprint_service=_make_chromaprint(),
            correlator=correlator,
        )

        result = detector.detect(_refs(3), _TUNING)

        assert result.analyzed_count == 2

    def test_passes_analysis_window_to_the_extractor(self) -> None:
        extractor = _make_audio_extractor()
        detector = ChromaprintIntroDetector(
            audio_extractor=extractor,
            chromaprint_service=_make_chromaprint(),
            correlator=_make_correlator(),
        )

        detector.detect(_refs(2), ChromaprintTuning(analysis_window_seconds=42))

        for call in extractor.extract_temporary.call_args_list:
            assert call.kwargs["duration_seconds"] == 42

    def test_returns_markers_from_the_correlator(self) -> None:
        ref = _refs(1)[0]
        marker = DetectedIntro(start_seconds=5.0, end_seconds=30.0, confidence=0.9)
        detector = ChromaprintIntroDetector(
            audio_extractor=_make_audio_extractor(),
            chromaprint_service=_make_chromaprint(),
            correlator=_make_correlator(markers={ref.episode_id: marker}),
        )

        result = detector.detect([ref], _TUNING)

        assert result.markers == {ref.episode_id: marker}

    def test_zero_analyzed_when_everything_fails(self) -> None:
        correlator = _make_correlator()
        detector = ChromaprintIntroDetector(
            audio_extractor=_make_audio_extractor(returns=[None, None]),
            chromaprint_service=_make_chromaprint(),
            correlator=correlator,
        )

        result = detector.detect(_refs(2), _TUNING)

        assert result.analyzed_count == 0
        # Correlator still invoked (with an empty list) — it short-circuits
        # on < 2 fingerprints and returns an empty map.
        assert correlator.correlate.call_args.args[0] == []


@pytest.mark.unit
class TestChromaprintIntroDetectorProgress:
    """The progress callback must fire once per episode, in order."""

    def test_reports_progress_for_every_episode(self) -> None:
        detector = ChromaprintIntroDetector(
            audio_extractor=_make_audio_extractor(),
            chromaprint_service=_make_chromaprint(),
            correlator=_make_correlator(),
        )
        refs = _refs(3)
        seen: list[tuple[int, int, EpisodeId]] = []

        detector.detect(refs, _TUNING, lambda *args: seen.append(args))

        assert [(done, total) for done, total, _ in seen] == [(1, 3), (2, 3), (3, 3)]
        assert [episode_id for _, _, episode_id in seen] == [r.episode_id for r in refs]

    def test_reports_progress_for_episodes_that_failed_to_fingerprint(self) -> None:
        """A dropped episode still advances the counter.

        Otherwise progress would stall on an unreadable file and read as
        a wedged run.
        """
        detector = ChromaprintIntroDetector(
            audio_extractor=_make_audio_extractor(returns=[None, Path("/tmp/ok.wav")]),
            chromaprint_service=_make_chromaprint(),
            correlator=_make_correlator(),
        )
        seen: list[int] = []

        detector.detect(_refs(2), _TUNING, lambda done, _t, _e: seen.append(done))

        assert seen == [1, 2]

    def test_works_without_a_callback(self) -> None:
        detector = ChromaprintIntroDetector(
            audio_extractor=_make_audio_extractor(),
            chromaprint_service=_make_chromaprint(),
            correlator=_make_correlator(),
        )

        result = detector.detect(_refs(2), _TUNING)

        assert result.analyzed_count == 2
