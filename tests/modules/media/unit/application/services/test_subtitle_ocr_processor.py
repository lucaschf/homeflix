"""Tests for SubtitleOcrProcessor (OCR one file's image subtitles)."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.modules.streaming.application.ports.subtitle_ocr_port import (
    OcrTrackResult,
    SubtitleOcrOptions,
    SubtitleOcrPort,
)
from src.modules.streaming.application.services.subtitle_ocr_processor import (
    SubtitleOcrProcessor,
)
from src.modules.streaming.domain.value_objects.subtitle_ocr_outcome import (
    SubtitleOcrOutcome,
    SubtitleTrackOutcome,
)
from src.shared_kernel.media_probe.media_probe_port import ProbeResult
from src.shared_kernel.value_objects.language_code import LanguageCode
from src.shared_kernel.value_objects.tracks import SubtitleTrack

_OPTS = SubtitleOcrOptions()
_OUT = Path("/tmp/out")


def _image(index: int, lang: str) -> SubtitleTrack:
    return SubtitleTrack(index=index, language=LanguageCode(lang), format="pgs")


def _text(index: int, lang: str) -> SubtitleTrack:
    return SubtitleTrack(index=index, language=LanguageCode(lang), format="srt")


def _processor(probe_tracks: list[SubtitleTrack], ocr_result: OcrTrackResult) -> tuple:
    probe = MagicMock()
    probe.probe.return_value = ProbeResult(subtitle_tracks=probe_tracks)
    ocr = MagicMock(spec=SubtitleOcrPort)
    ocr.ocr_track.return_value = ocr_result
    return SubtitleOcrProcessor(probe, ocr), ocr


@pytest.mark.unit
class TestSubtitleOcrProcessor:
    def test_no_image_tracks(self) -> None:
        proc, ocr = _processor(
            [_text(0, "en")], OcrTrackResult(outcome=SubtitleTrackOutcome.EXTRACTED)
        )

        report = proc.process_file("m.mkv", _OUT, _OPTS, None)

        assert report.outcome == SubtitleOcrOutcome.NO_IMAGE_SUBTITLES
        assert report.image_track_count == 0
        assert report.track_results == []
        ocr.ocr_track.assert_not_called()

    def test_extracts_each_image_track(self) -> None:
        proc, ocr = _processor(
            [_image(0, "en"), _image(1, "pt")],
            OcrTrackResult(outcome=SubtitleTrackOutcome.EXTRACTED, cue_count=50),
        )

        report = proc.process_file("m.mkv", _OUT, _OPTS, None)

        assert report.outcome == SubtitleOcrOutcome.COMPLETED
        assert report.image_track_count == 2
        assert report.extracted_count == 2
        assert [r.language for r in report.track_results] == ["en", "pt"]
        assert report.track_results[0].cue_count == 50

    def test_language_filter_marks_skipped_without_ocr(self) -> None:
        proc, ocr = _processor(
            [_image(0, "en"), _image(1, "pt")],
            OcrTrackResult(outcome=SubtitleTrackOutcome.EXTRACTED, cue_count=10),
        )

        report = proc.process_file("m.mkv", _OUT, _OPTS, frozenset({"pt"}))

        assert ocr.ocr_track.call_count == 1  # only the pt track
        by_lang = {r.language: r.outcome for r in report.track_results}
        assert by_lang["en"] == SubtitleTrackOutcome.SKIPPED_LANGUAGE
        assert by_lang["pt"] == SubtitleTrackOutcome.EXTRACTED
        assert report.extracted_count == 1

    def test_non_extracted_outcome_flows_through(self) -> None:
        proc, _ = _processor(
            [_image(0, "en")],
            OcrTrackResult(outcome=SubtitleTrackOutcome.NO_TEXT),
        )

        report = proc.process_file("m.mkv", _OUT, _OPTS, None)

        assert report.outcome == SubtitleOcrOutcome.COMPLETED
        assert report.extracted_count == 0
        assert report.track_results[0].outcome == SubtitleTrackOutcome.NO_TEXT
