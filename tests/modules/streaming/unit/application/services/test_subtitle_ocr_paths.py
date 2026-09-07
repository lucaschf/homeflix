"""Tests for the OCR sidecar path helpers."""

from pathlib import Path

import pytest

from src.modules.streaming.application.services.subtitle_ocr_paths import (
    ocr_subtitle_output_dir,
)

_SUBDIR = ".homeflix/subtitles"


@pytest.mark.unit
class TestOcrSubtitleOutputDir:
    def test_nests_one_folder_per_stem_under_subdir(self) -> None:
        source = Path("/movies/Inception (2010)/Inception (2010).mkv")

        out = ocr_subtitle_output_dir(source, _SUBDIR)

        assert out == source.parent / _SUBDIR / "Inception (2010)"

    def test_strips_trailing_spaces_and_dots_from_stem(self) -> None:
        # Windows drops trailing spaces/dots when creating a directory, so
        # the predicted path must match what actually lands on disk.
        source = Path("/movies/Black Killer (1971)/Black Killer (1971) .mkv")

        out = ocr_subtitle_output_dir(source, _SUBDIR)

        assert out == source.parent / _SUBDIR / "Black Killer (1971)"

    def test_marker_is_writable_for_trailing_space_stem(self, tmp_path: Path) -> None:
        source = tmp_path / "Black Killer (1971) .mkv"
        out = ocr_subtitle_output_dir(source, _SUBDIR)
        out.mkdir(parents=True, exist_ok=True)

        (out / ".ocr_done").write_text("", encoding="utf-8")

        assert (out / ".ocr_done").is_file()
