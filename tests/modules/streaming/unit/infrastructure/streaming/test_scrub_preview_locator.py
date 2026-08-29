"""Tests for FilesystemScrubPreviewLocator."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.modules.settings.domain.value_objects import ThumbnailBackfillConfig
from src.modules.streaming.infrastructure.streaming.scrub_preview_locator import (
    FilesystemScrubPreviewLocator,
)
from src.modules.streaming.infrastructure.streaming.thumbnail_service import (
    SPRITE_FILENAME,
    VTT_FILENAME,
    scrub_preview_output_dir,
)

_SUBDIR = ".homeflix/thumbnails"


def _locator(subdir: str = _SUBDIR) -> FilesystemScrubPreviewLocator:
    runtime = MagicMock()
    runtime.thumbnail_backfill = AsyncMock(
        return_value=ThumbnailBackfillConfig(batch_size=10, subdir=subdir),
    )
    return FilesystemScrubPreviewLocator(runtime_settings=runtime)


def _write_preview(
    source: Path, subdir: str = _SUBDIR, *, vtt: bool = True, sprite: bool = True
) -> Path:
    output_dir = scrub_preview_output_dir(source, subdir)
    output_dir.mkdir(parents=True, exist_ok=True)
    if vtt:
        (output_dir / VTT_FILENAME).write_text("WEBVTT\n")
    if sprite:
        (output_dir / SPRITE_FILENAME).write_bytes(b"\xff\xd8\xff")
    return output_dir / VTT_FILENAME


@pytest.mark.unit
class TestFilesystemScrubPreviewLocator:
    @pytest.mark.asyncio
    async def test_should_return_vtt_path_when_both_files_present(self, tmp_path: Path) -> None:
        source = tmp_path / "movies" / "Inception.mkv"
        source.parent.mkdir(parents=True)
        source.write_bytes(b"\x00")
        expected_vtt = _write_preview(source)

        result = await _locator().locate(str(source))

        assert result == str(expected_vtt)

    @pytest.mark.asyncio
    async def test_should_return_none_when_sprite_missing(self, tmp_path: Path) -> None:
        source = tmp_path / "movies" / "Inception.mkv"
        source.parent.mkdir(parents=True)
        _write_preview(source, sprite=False)

        result = await _locator().locate(str(source))

        assert result is None

    @pytest.mark.asyncio
    async def test_should_return_none_when_vtt_missing(self, tmp_path: Path) -> None:
        source = tmp_path / "movies" / "Inception.mkv"
        source.parent.mkdir(parents=True)
        _write_preview(source, vtt=False)

        result = await _locator().locate(str(source))

        assert result is None

    @pytest.mark.asyncio
    async def test_should_return_none_when_nothing_on_disk(self, tmp_path: Path) -> None:
        source = tmp_path / "movies" / "Inception.mkv"

        result = await _locator().locate(str(source))

        assert result is None

    @pytest.mark.asyncio
    async def test_should_honour_configured_subdir(self, tmp_path: Path) -> None:
        source = tmp_path / "movies" / "Inception.mkv"
        source.parent.mkdir(parents=True)
        expected_vtt = _write_preview(source, subdir="custom/previews")

        result = await _locator(subdir="custom/previews").locate(str(source))

        assert result == str(expected_vtt)


@pytest.mark.unit
class TestScrubPreviewOutputDir:
    def test_should_build_per_stem_directory(self) -> None:
        source = Path("/media/Show/S01/Show.S01E01.mkv")

        output_dir = scrub_preview_output_dir(source, ".homeflix/thumbnails")

        assert output_dir == Path(
            "/media/Show/S01/.homeflix/thumbnails/Show.S01E01",
        )
