"""Tests for SubtitleOcrBackfillJob.

Stubs the media UoW, probe, and OCR service so the tests exercise the
job's orchestration — the enabled/availability gates, the marker-based
discovery, the batch budget, and the language filter — without touching
the database, ffmpeg, or tesseract.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.infrastructure.scheduling.subtitle_ocr_job import (
    OCR_DONE_MARKER,
    SubtitleOcrBackfillJob,
)
from src.modules.media.application.ports.media_probe_port import ProbeResult
from src.modules.media.application.ports.subtitle_ocr_port import SubtitleOcrPort
from src.modules.media.infrastructure.streaming.subtitle_ocr_service import (
    ocr_subtitle_output_dir,
)
from src.modules.settings.domain.value_objects import StreamingConfig, SubtitleOcrConfig
from src.shared_kernel.value_objects.language_code import LanguageCode
from src.shared_kernel.value_objects.tracks import SubtitleTrack

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

_SUBDIR = ".homeflix/subtitles"


def _entity(path: Path | None) -> SimpleNamespace:
    if path is None:
        return SimpleNamespace(primary_file=None)
    return SimpleNamespace(primary_file=SimpleNamespace(file_path=SimpleNamespace(value=str(path))))


def _series(episode_paths: Iterable[Path]) -> SimpleNamespace:
    episodes = [_entity(p) for p in episode_paths]
    return SimpleNamespace(seasons=[SimpleNamespace(episodes=episodes)])


def _build_uow(*, movies: list, series: list) -> AsyncMock:
    uow = AsyncMock()
    uow.__aenter__.return_value = uow
    uow.__aexit__.return_value = None
    uow.movies = AsyncMock()
    uow.movies.list_all = AsyncMock(return_value=movies)
    uow.series = AsyncMock()
    uow.series.list_all = AsyncMock(return_value=series)
    return uow


def _runtime_settings(config: SubtitleOcrConfig) -> AsyncMock:
    runtime = AsyncMock()
    runtime.subtitle_ocr = AsyncMock(return_value=config)
    runtime.streaming = AsyncMock(return_value=StreamingConfig())
    return runtime


def _ocr_service(*, langs: frozenset[str] = frozenset({"eng", "por"})) -> MagicMock:
    service = MagicMock(spec=SubtitleOcrPort)
    service.available_languages.return_value = langs
    service.ocr_track.return_value = None
    return service


def _probe_with(*tracks: SubtitleTrack) -> MagicMock:
    probe = MagicMock()
    probe.probe.return_value = ProbeResult(subtitle_tracks=list(tracks))
    return probe


def _image(index: int = 0, lang: str = "en") -> SubtitleTrack:
    return SubtitleTrack(index=index, language=LanguageCode(lang), format="pgs")


def _text(index: int = 0, lang: str = "en") -> SubtitleTrack:
    return SubtitleTrack(index=index, language=LanguageCode(lang), format="srt")


def _touch(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")
    return path


def _marker(source: Path) -> Path:
    return ocr_subtitle_output_dir(source, _SUBDIR) / OCR_DONE_MARKER


def _make_job(uow: AsyncMock, config: SubtitleOcrConfig, probe: MagicMock, ocr: MagicMock):
    return SubtitleOcrBackfillJob(
        media_uow_factory=MagicMock(return_value=uow),
        runtime_settings=_runtime_settings(config),
        ocr_service=ocr,
        probe_service=probe,
    )


@pytest.mark.unit
@pytest.mark.asyncio
class TestSubtitleOcrBackfillJob:
    async def test_disabled_does_nothing(self, tmp_path: Path) -> None:
        movie = _touch(tmp_path / "m.mkv")
        uow = _build_uow(movies=[_entity(movie)], series=[])
        probe, ocr = _probe_with(_image()), _ocr_service()
        job = _make_job(uow, SubtitleOcrConfig(enabled=False), probe, ocr)

        await job.run()

        probe.probe.assert_not_called()
        ocr.ocr_track.assert_not_called()
        assert not _marker(movie).exists()

    async def test_no_installed_languages_skips_tick(self, tmp_path: Path) -> None:
        movie = _touch(tmp_path / "m.mkv")
        uow = _build_uow(movies=[_entity(movie)], series=[])
        probe = _probe_with(_image())
        ocr = _ocr_service(langs=frozenset())
        job = _make_job(uow, SubtitleOcrConfig(enabled=True), probe, ocr)

        await job.run()

        probe.probe.assert_not_called()
        ocr.ocr_track.assert_not_called()
        assert not _marker(movie).exists()

    async def test_ocrs_image_track_and_writes_marker(self, tmp_path: Path) -> None:
        movie = _touch(tmp_path / "m.mkv")
        uow = _build_uow(movies=[_entity(movie)], series=[])
        image = _image(lang="pt")
        probe, ocr = _probe_with(image), _ocr_service()
        job = _make_job(uow, SubtitleOcrConfig(enabled=True), probe, ocr)

        await job.run()

        ocr.ocr_track.assert_called_once()
        assert ocr.ocr_track.call_args.args[1] is image
        assert _marker(movie).exists()

    async def test_marked_file_is_skipped(self, tmp_path: Path) -> None:
        movie = _touch(tmp_path / "m.mkv")
        _touch(_marker(movie))  # already processed
        uow = _build_uow(movies=[_entity(movie)], series=[])
        probe, ocr = _probe_with(_image()), _ocr_service()
        job = _make_job(uow, SubtitleOcrConfig(enabled=True), probe, ocr)

        await job.run()

        probe.probe.assert_not_called()
        ocr.ocr_track.assert_not_called()

    async def test_batch_size_bounds_files_processed(self, tmp_path: Path) -> None:
        movies = [_touch(tmp_path / f"m{i}.mkv") for i in range(3)]
        uow = _build_uow(movies=[_entity(m) for m in movies], series=[])
        probe, ocr = _probe_with(_image()), _ocr_service()
        job = _make_job(uow, SubtitleOcrConfig(enabled=True, batch_size=2), probe, ocr)

        await job.run()

        assert sum(_marker(m).exists() for m in movies) == 2

    async def test_language_filter_skips_other_languages_but_marks(self, tmp_path: Path) -> None:
        movie = _touch(tmp_path / "m.mkv")
        uow = _build_uow(movies=[_entity(movie)], series=[])
        probe = _probe_with(_image(lang="en"))  # only English image track
        ocr = _ocr_service()
        job = _make_job(uow, SubtitleOcrConfig(enabled=True, languages=("pt",)), probe, ocr)

        await job.run()

        ocr.ocr_track.assert_not_called()  # en filtered out
        assert _marker(movie).exists()  # still marked attempted

    async def test_non_image_tracks_are_ignored_but_file_marked(self, tmp_path: Path) -> None:
        movie = _touch(tmp_path / "m.mkv")
        uow = _build_uow(movies=[_entity(movie)], series=[])
        probe, ocr = _probe_with(_text()), _ocr_service()
        job = _make_job(uow, SubtitleOcrConfig(enabled=True), probe, ocr)

        await job.run()

        ocr.ocr_track.assert_not_called()
        assert _marker(movie).exists()

    async def test_episodes_processed_when_budget_remains(self, tmp_path: Path) -> None:
        episode = _touch(tmp_path / "e1.mkv")
        uow = _build_uow(movies=[], series=[_series([episode])])
        image = _image()
        probe, ocr = _probe_with(image), _ocr_service()
        job = _make_job(uow, SubtitleOcrConfig(enabled=True), probe, ocr)

        await job.run()

        ocr.ocr_track.assert_called_once()
        assert _marker(episode).exists()

    async def test_missing_source_file_is_skipped(self, tmp_path: Path) -> None:
        missing = tmp_path / "gone.mkv"  # never created
        uow = _build_uow(movies=[_entity(missing)], series=[])
        probe, ocr = _probe_with(_image()), _ocr_service()
        job = _make_job(uow, SubtitleOcrConfig(enabled=True), probe, ocr)

        await job.run()

        probe.probe.assert_not_called()
        assert not _marker(missing).exists()
