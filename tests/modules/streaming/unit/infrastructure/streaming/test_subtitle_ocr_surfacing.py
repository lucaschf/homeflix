"""Tests for surfacing OCR sidecars as external text tracks (ADR-027)."""

from pathlib import Path

import pytest

from src.modules.settings.domain.value_objects import SubtitleOcrConfig
from src.modules.streaming.infrastructure.streaming.subtitle_ocr_service import (
    ocr_sidecar_filename,
    ocr_subtitle_output_dir,
)
from src.modules.streaming.infrastructure.streaming.subtitle_ocr_surfacing import (
    attach_ocr_subtitles,
)
from src.shared_kernel.media_probe.media_probe_port import ProbeResult
from src.shared_kernel.value_objects.language_code import LanguageCode
from src.shared_kernel.value_objects.tracks import SubtitleTrack

_SUBDIR = ".homeflix/subtitles"


def _text(index: int, lang: str = "en") -> SubtitleTrack:
    return SubtitleTrack(index=index, language=LanguageCode(lang), format="srt")


def _image(index: int, lang: str = "pt", *, forced: bool = False) -> SubtitleTrack:
    return SubtitleTrack(index=index, language=LanguageCode(lang), format="pgs", is_forced=forced)


def _probe(*subs: SubtitleTrack) -> ProbeResult:
    embedded = [s for s in subs if not s.is_external]
    external = [s for s in subs if s.is_external]
    return ProbeResult(subtitle_tracks=list(embedded), external_subtitles=list(external))


def _write_sidecar(source: Path, track: SubtitleTrack) -> Path:
    out = ocr_subtitle_output_dir(source, _SUBDIR)
    out.mkdir(parents=True, exist_ok=True)
    sidecar = out / ocr_sidecar_filename(track)
    sidecar.write_text("WEBVTT\n", encoding="utf-8")
    return sidecar


def _source(tmp_path: Path) -> Path:
    source = tmp_path / "Movie (2020)" / "Movie (2020).mkv"
    source.parent.mkdir(parents=True, exist_ok=True)
    return source


@pytest.mark.unit
class TestAttachOcrSubtitles:
    def test_disabled_is_a_noop(self, tmp_path: Path) -> None:
        source = _source(tmp_path)
        image = _image(1)
        _write_sidecar(source, image)  # sidecar exists but OCR is off
        probe = _probe(_text(0), image)

        result = attach_ocr_subtitles(probe, str(source), SubtitleOcrConfig(enabled=False))

        assert result is probe

    def test_surfaces_image_track_with_existing_sidecar(self, tmp_path: Path) -> None:
        source = _source(tmp_path)
        image = _image(1, lang="pt", forced=True)
        sidecar = _write_sidecar(source, image)
        probe = _probe(_text(0), image)

        result = attach_ocr_subtitles(probe, str(source), SubtitleOcrConfig(enabled=True))

        ocr = [t for t in result.all_subtitles if t.format == "vtt"]
        assert len(ocr) == 1
        assert ocr[0].index == 2  # max(0, 1) + 1
        assert ocr[0].is_external is True
        assert ocr[0].file_path is not None
        assert ocr[0].file_path.value == str(sidecar)
        assert ocr[0].language.value == "pt"
        assert ocr[0].is_forced is True
        # original image track is preserved untouched
        assert any(t.format == "pgs" for t in result.all_subtitles)

    def test_image_track_without_sidecar_is_unchanged(self, tmp_path: Path) -> None:
        source = _source(tmp_path)
        probe = _probe(_text(0), _image(1))

        result = attach_ocr_subtitles(probe, str(source), SubtitleOcrConfig(enabled=True))

        assert result is probe

    def test_no_image_tracks_is_unchanged(self, tmp_path: Path) -> None:
        source = _source(tmp_path)
        probe = _probe(_text(0), _text(1, "pt"))

        result = attach_ocr_subtitles(probe, str(source), SubtitleOcrConfig(enabled=True))

        assert result is probe

    def test_multiple_sidecars_get_distinct_indices_past_max(self, tmp_path: Path) -> None:
        source = _source(tmp_path)
        img_pt = _image(3, lang="pt")
        img_en = _image(4, lang="en")
        for track in (img_pt, img_en):
            _write_sidecar(source, track)
        probe = _probe(_text(0), img_pt, img_en)

        result = attach_ocr_subtitles(probe, str(source), SubtitleOcrConfig(enabled=True))

        ocr_indices = sorted(t.index for t in result.all_subtitles if t.format == "vtt")
        assert ocr_indices == [5, 6]  # max(0,3,4)+1, +2 — no collision with sub_N

    def test_only_tracks_with_sidecars_are_surfaced(self, tmp_path: Path) -> None:
        source = _source(tmp_path)
        img_with = _image(1, lang="pt")
        img_without = _image(2, lang="en")
        _write_sidecar(source, img_with)
        probe = _probe(img_with, img_without)

        result = attach_ocr_subtitles(probe, str(source), SubtitleOcrConfig(enabled=True))

        ocr = [t for t in result.all_subtitles if t.format == "vtt"]
        assert [t.language.value for t in ocr] == ["pt"]
