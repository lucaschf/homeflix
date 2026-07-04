"""Tests for SubtitleOcrBackfillJob.

Stubs the media UoW, probe, and OCR service so the tests exercise the
job's orchestration — the enabled/availability gates, the marker-based
discovery, the batch budget, the language filter, and the audit-run
recording — without touching the database, ffmpeg, or tesseract.
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
from src.modules.media.application.ports.subtitle_ocr_port import (
    OcrTrackResult,
    SubtitleOcrPort,
)
from src.modules.media.domain.value_objects.subtitle_ocr_outcome import (
    SubtitleOcrOutcome,
    SubtitleTrackOutcome,
)
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


def _movie(path: Path | None, *, media_id: str = "mov_1", title: str = "Movie") -> SimpleNamespace:
    primary = None if path is None else SimpleNamespace(file_path=SimpleNamespace(value=str(path)))
    return SimpleNamespace(id=media_id, title=SimpleNamespace(value=title), primary_file=primary)


def _series(episode_paths: Iterable[Path], *, title: str = "Show") -> SimpleNamespace:
    episodes = [
        SimpleNamespace(
            id=f"epi_{i}",
            season_number=SimpleNamespace(value=1),
            episode_number=SimpleNamespace(value=i + 1),
            primary_file=SimpleNamespace(file_path=SimpleNamespace(value=str(p))),
        )
        for i, p in enumerate(episode_paths)
    ]
    return SimpleNamespace(
        title=SimpleNamespace(value=title), seasons=[SimpleNamespace(episodes=episodes)]
    )


def _build_uow(*, movies: list, series: list) -> AsyncMock:
    uow = AsyncMock()
    uow.__aenter__.return_value = uow
    uow.__aexit__.return_value = None
    uow.movies = AsyncMock()
    uow.movies.list_all = AsyncMock(return_value=movies)
    uow.series = AsyncMock()
    uow.series.list_all = AsyncMock(return_value=series)
    uow.subtitle_ocr_runs = AsyncMock()
    return uow


def _runtime_settings(config: SubtitleOcrConfig) -> AsyncMock:
    runtime = AsyncMock()
    runtime.subtitle_ocr = AsyncMock(return_value=config)
    runtime.streaming = AsyncMock(return_value=StreamingConfig())
    return runtime


def _ocr_service(
    *,
    langs: frozenset[str] = frozenset({"eng", "por"}),
    outcome: SubtitleTrackOutcome = SubtitleTrackOutcome.EXTRACTED,
    cue_count: int = 12,
) -> MagicMock:
    service = MagicMock(spec=SubtitleOcrPort)
    service.available_languages.return_value = langs
    service.ocr_track.return_value = OcrTrackResult(outcome=outcome, cue_count=cue_count)
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


def _recorded_runs(uow: AsyncMock) -> list:
    return [call.args[0] for call in uow.subtitle_ocr_runs.add.call_args_list]


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
        uow = _build_uow(movies=[_movie(movie)], series=[])
        probe, ocr = _probe_with(_image()), _ocr_service()
        job = _make_job(uow, SubtitleOcrConfig(enabled=False), probe, ocr)

        await job.run()

        probe.probe.assert_not_called()
        ocr.ocr_track.assert_not_called()
        assert not _marker(movie).exists()

    async def test_no_installed_languages_skips_tick(self, tmp_path: Path) -> None:
        movie = _touch(tmp_path / "m.mkv")
        uow = _build_uow(movies=[_movie(movie)], series=[])
        probe = _probe_with(_image())
        ocr = _ocr_service(langs=frozenset())
        job = _make_job(uow, SubtitleOcrConfig(enabled=True), probe, ocr)

        await job.run()

        probe.probe.assert_not_called()
        ocr.ocr_track.assert_not_called()
        assert not _marker(movie).exists()

    async def test_ocrs_image_track_writes_marker_and_records_run(self, tmp_path: Path) -> None:
        movie = _touch(tmp_path / "m.mkv")
        uow = _build_uow(movies=[_movie(movie, media_id="mov_42", title="Nausicaa")], series=[])
        image = _image(lang="pt")
        probe, ocr = _probe_with(image), _ocr_service(cue_count=99)
        job = _make_job(uow, SubtitleOcrConfig(enabled=True), probe, ocr)

        await job.run()

        ocr.ocr_track.assert_called_once()
        assert ocr.ocr_track.call_args.args[1] is image
        assert _marker(movie).exists()

        runs = _recorded_runs(uow)
        assert len(runs) == 1
        run = runs[0]
        assert run.media_kind == "movie"
        assert run.media_id == "mov_42"
        assert run.media_title == "Nausicaa"
        assert run.outcome == SubtitleOcrOutcome.COMPLETED
        assert run.image_track_count == 1
        assert run.extracted_count == 1
        assert run.track_results[0].language == "pt"
        assert run.track_results[0].cue_count == 99

    async def test_marked_file_is_skipped(self, tmp_path: Path) -> None:
        movie = _touch(tmp_path / "m.mkv")
        _touch(_marker(movie))  # already processed
        uow = _build_uow(movies=[_movie(movie)], series=[])
        probe, ocr = _probe_with(_image()), _ocr_service()
        job = _make_job(uow, SubtitleOcrConfig(enabled=True), probe, ocr)

        await job.run()

        probe.probe.assert_not_called()
        ocr.ocr_track.assert_not_called()
        assert _recorded_runs(uow) == []

    async def test_batch_size_bounds_files_processed(self, tmp_path: Path) -> None:
        movies = [_touch(tmp_path / f"m{i}.mkv") for i in range(3)]
        uow = _build_uow(
            movies=[_movie(m, media_id=f"mov_{i}") for i, m in enumerate(movies)], series=[]
        )
        probe, ocr = _probe_with(_image()), _ocr_service()
        job = _make_job(uow, SubtitleOcrConfig(enabled=True, batch_size=2), probe, ocr)

        await job.run()

        assert sum(_marker(m).exists() for m in movies) == 2

    async def test_language_filter_records_skipped_and_does_not_ocr(self, tmp_path: Path) -> None:
        movie = _touch(tmp_path / "m.mkv")
        uow = _build_uow(movies=[_movie(movie)], series=[])
        probe = _probe_with(_image(lang="en"))  # only English image track
        ocr = _ocr_service()
        job = _make_job(uow, SubtitleOcrConfig(enabled=True, languages=("pt",)), probe, ocr)

        await job.run()

        ocr.ocr_track.assert_not_called()  # en filtered out
        assert _marker(movie).exists()
        run = _recorded_runs(uow)[0]
        assert run.image_track_count == 1
        assert run.extracted_count == 0
        assert run.track_results[0].outcome == SubtitleTrackOutcome.SKIPPED_LANGUAGE

    async def test_no_image_tracks_marks_but_records_no_run(self, tmp_path: Path) -> None:
        movie = _touch(tmp_path / "m.mkv")
        uow = _build_uow(movies=[_movie(movie)], series=[])
        probe, ocr = _probe_with(_text()), _ocr_service()
        job = _make_job(uow, SubtitleOcrConfig(enabled=True), probe, ocr)

        await job.run()

        ocr.ocr_track.assert_not_called()
        assert _marker(movie).exists()
        assert _recorded_runs(uow) == []  # nothing to observe -> no audit noise

    async def test_episodes_processed_when_budget_remains(self, tmp_path: Path) -> None:
        episode = _touch(tmp_path / "e1.mkv")
        uow = _build_uow(movies=[], series=[_series([episode], title="Show")])
        image = _image()
        probe, ocr = _probe_with(image), _ocr_service()
        job = _make_job(uow, SubtitleOcrConfig(enabled=True), probe, ocr)

        await job.run()

        ocr.ocr_track.assert_called_once()
        assert _marker(episode).exists()
        run = _recorded_runs(uow)[0]
        assert run.media_kind == "episode"
        assert run.media_title == "Show S01E01"

    async def test_missing_source_file_is_skipped(self, tmp_path: Path) -> None:
        missing = tmp_path / "gone.mkv"  # never created
        uow = _build_uow(movies=[_movie(missing)], series=[])
        probe, ocr = _probe_with(_image()), _ocr_service()
        job = _make_job(uow, SubtitleOcrConfig(enabled=True), probe, ocr)

        await job.run()

        probe.probe.assert_not_called()
        assert not _marker(missing).exists()
