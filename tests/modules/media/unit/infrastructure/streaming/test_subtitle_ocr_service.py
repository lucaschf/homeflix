"""Tests for the tesseract PGS OCR service (ADR-027).

The real tesseract/ffmpeg binaries are never invoked: the parse step,
the language probe, the bitmap read, and the per-cue OCR are stubbed so
the orchestration (filtering, VTT assembly, degradation to ``None``) is
verified deterministically.
"""

from pathlib import Path

import pytest
from PIL import Image

from src.modules.media.application.ports.subtitle_ocr_port import SubtitleOcrOptions
from src.modules.media.domain.value_objects.subtitle_ocr_outcome import SubtitleTrackOutcome
from src.modules.media.infrastructure.streaming import subtitle_ocr_service as svc
from src.modules.media.infrastructure.streaming.pgs_parser import PgsCue
from src.modules.media.infrastructure.streaming.subtitle_ocr_service import (
    TesseractPgsOcrService,
    ocr_sidecar_filename,
    ocr_subtitle_output_dir,
)
from src.shared_kernel.value_objects.file_path import FilePath
from src.shared_kernel.value_objects.language_code import LanguageCode
from src.shared_kernel.value_objects.tracks import SubtitleTrack

_OPTS = SubtitleOcrOptions(tesseract_binary="tesseract", per_cue_timeout_seconds=5)


def _pgs_track(index: int = 4, lang: str = "pt") -> SubtitleTrack:
    return SubtitleTrack(index=index, language=LanguageCode(lang), format="pgs")


def _cue(start_ms: int, end_ms: int) -> PgsCue:
    return PgsCue(start_ms, end_ms, Image.new("RGBA", (2, 1)))


@pytest.mark.unit
class TestOcrTrack:
    def test_unsupported_bitmap_format_is_skipped(self, tmp_path: Path) -> None:
        track = SubtitleTrack(index=1, language=LanguageCode("en"), format="vobsub")
        service = TesseractPgsOcrService()

        result = service.ocr_track("movie.mkv", track, tmp_path, _OPTS)

        assert result.outcome == SubtitleTrackOutcome.UNSUPPORTED_FORMAT
        assert result.vtt_path is None

    def test_unmappable_language_is_skipped(self, tmp_path: Path) -> None:
        # "th" (Thai) is a valid ISO code but not in the model map.
        service = TesseractPgsOcrService()

        result = service.ocr_track("m.mkv", _pgs_track(lang="th"), tmp_path, _OPTS)

        assert result.outcome == SubtitleTrackOutcome.NO_LANGUAGE_MODEL

    def test_missing_language_model_is_skipped(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        service = TesseractPgsOcrService()
        monkeypatch.setattr(service, "_available_langs", lambda _binary: frozenset())

        result = service.ocr_track("m.mkv", _pgs_track(), tmp_path, _OPTS)

        assert result.outcome == SubtitleTrackOutcome.NO_LANGUAGE_MODEL

    def test_writes_vtt_sidecar_on_success(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        service = TesseractPgsOcrService()
        monkeypatch.setattr(service, "_available_langs", lambda _binary: frozenset({"por"}))
        monkeypatch.setattr(service, "_read_pgs_bytes", lambda *a: b"rawpgs")
        monkeypatch.setattr(svc, "parse_pgs", lambda _raw: [_cue(1000, 2000), _cue(3000, 4000)])
        texts = iter(["Olá mundo", "Segunda linha"])
        monkeypatch.setattr(service, "_ocr_one", lambda *a: next(texts))

        track = _pgs_track(index=4, lang="pt")
        result = service.ocr_track("m.mkv", track, tmp_path, _OPTS)

        assert result.outcome == SubtitleTrackOutcome.EXTRACTED
        assert result.vtt_path == tmp_path / "ocr_s4_pt.vtt"
        assert result.cue_count == 2
        content = result.vtt_path.read_text(encoding="utf-8")
        assert content.startswith("WEBVTT")
        assert "00:00:01.000 --> 00:00:02.000" in content
        assert "Olá mundo" in content
        assert "00:00:03.000 --> 00:00:04.000" in content

    def test_all_empty_ocr_yields_no_sidecar(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        service = TesseractPgsOcrService()
        monkeypatch.setattr(service, "_available_langs", lambda _binary: frozenset({"por"}))
        monkeypatch.setattr(service, "_read_pgs_bytes", lambda *a: b"rawpgs")
        monkeypatch.setattr(svc, "parse_pgs", lambda _raw: [_cue(1000, 2000)])
        monkeypatch.setattr(service, "_ocr_one", lambda *a: "")

        result = service.ocr_track("m.mkv", _pgs_track(), tmp_path, _OPTS)

        assert result.outcome == SubtitleTrackOutcome.NO_TEXT
        assert result.vtt_path is None
        assert list(tmp_path.glob("*.vtt")) == []

    def test_no_cues_parsed_yields_no_sidecar(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        service = TesseractPgsOcrService()
        monkeypatch.setattr(service, "_available_langs", lambda _binary: frozenset({"por"}))
        monkeypatch.setattr(service, "_read_pgs_bytes", lambda *a: b"rawpgs")
        monkeypatch.setattr(svc, "parse_pgs", lambda _raw: [])

        result = service.ocr_track("m.mkv", _pgs_track(), tmp_path, _OPTS)

        assert result.outcome == SubtitleTrackOutcome.NO_TEXT

    def test_external_sup_reads_file_directly(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sup = tmp_path / "sub.sup"
        sup.write_bytes(b"rawpgs")
        track = SubtitleTrack(
            index=7,
            language=LanguageCode("en"),
            format="sup",
            is_external=True,
            file_path=FilePath(str(sup)),
        )
        service = TesseractPgsOcrService()
        monkeypatch.setattr(service, "_available_langs", lambda _binary: frozenset({"eng"}))
        captured: dict[str, bytes] = {}
        monkeypatch.setattr(svc, "parse_pgs", lambda raw: captured.setdefault("raw", raw) and [])

        service.ocr_track("m.mkv", track, tmp_path, _OPTS)

        assert captured["raw"] == b"rawpgs"


@pytest.mark.unit
class TestHelpers:
    def test_sidecar_filename_is_deterministic_from_track(self) -> None:
        assert ocr_sidecar_filename(_pgs_track(index=4, lang="pt")) == "ocr_s4_pt.vtt"

    def test_output_dir_mirrors_scrub_preview_layout(self) -> None:
        source = Path("/media/Movies/Film (2020)/Film (2020).mkv")

        out = ocr_subtitle_output_dir(source, ".homeflix/subtitles")

        assert out == source.parent / ".homeflix/subtitles" / "Film (2020)"

    def test_clean_text_fixes_pipe_misread(self) -> None:
        assert svc._clean_ocr_text("| wonder if | can go") == "I wonder if I can go"

    def test_clean_text_drops_blank_lines_and_trims(self) -> None:
        assert svc._clean_ocr_text("\n  Hello  \n\n world \n") == "Hello\nworld"

    def test_ms_to_vtt_formats_timestamp(self) -> None:
        assert svc._ms_to_vtt(3_661_007) == "01:01:01.007"

    def test_render_vtt_has_header_and_blank_separated_cues(self) -> None:
        out = svc._render_vtt([(1000, 2000, "A"), (3000, 4000, "B")])

        assert out.startswith("WEBVTT\n\n")
        assert "00:00:01.000 --> 00:00:02.000\nA\n" in out
