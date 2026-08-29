"""Tests for RunSubtitleOcrForMediaUseCase (manual OCR trigger)."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.building_blocks.application.errors import ResourceNotFoundException
from src.modules.settings.domain.value_objects import StreamingConfig, SubtitleOcrConfig
from src.modules.streaming.application.dtos.subtitle_ocr_run_dtos import RunSubtitleOcrInput
from src.modules.streaming.application.ports.media_lookup_port import MediaSourceInfo
from src.modules.streaming.application.services.subtitle_ocr_paths import (
    OCR_DONE_MARKER,
    ocr_subtitle_output_dir,
)
from src.modules.streaming.application.services.subtitle_ocr_processor import FileOcrReport
from src.modules.streaming.application.use_cases.run_subtitle_ocr_for_media import (
    RunSubtitleOcrForMediaUseCase,
)
from src.modules.streaming.domain.entities.subtitle_ocr_run import SubtitleTrackOcrResult
from src.modules.streaming.domain.value_objects.subtitle_ocr_outcome import (
    SubtitleOcrOutcome,
    SubtitleTrackOutcome,
)
from src.modules.streaming.domain.value_objects.subtitle_ocr_run_id import SubtitleOcrRunId

if TYPE_CHECKING:
    from pathlib import Path


def _lookup(
    *,
    movie_source: MediaSourceInfo | None = None,
    episode_source: MediaSourceInfo | None = None,
) -> MagicMock:
    lookup = MagicMock()
    lookup.find_movie_source = AsyncMock(return_value=movie_source)
    lookup.find_episode_source = AsyncMock(return_value=episode_source)
    return lookup


def _uow() -> AsyncMock:
    uow = AsyncMock()
    uow.__aenter__.return_value = uow
    uow.__aexit__.return_value = None
    uow.subtitle_ocr_runs = AsyncMock()
    uow.subtitle_ocr_runs.add = AsyncMock(
        side_effect=lambda run: run.with_updates(id=SubtitleOcrRunId.generate())
    )
    return uow


def _config(languages: tuple[str, ...] = ()) -> AsyncMock:
    config = AsyncMock()
    config.subtitle_ocr = AsyncMock(return_value=SubtitleOcrConfig(languages=languages))
    config.streaming = AsyncMock(return_value=StreamingConfig())
    return config


def _ocr_service(*, langs: frozenset[str] = frozenset({"eng", "por"})) -> MagicMock:
    service = MagicMock()
    service.available_languages.return_value = langs
    return service


def _processor(report: FileOcrReport) -> MagicMock:
    proc = MagicMock()
    proc.process_file.return_value = report
    return proc


def _use_case(
    lookup: MagicMock,
    uow: AsyncMock,
    processor: MagicMock,
    ocr: MagicMock,
    languages: tuple[str, ...] = (),
) -> RunSubtitleOcrForMediaUseCase:
    return RunSubtitleOcrForMediaUseCase(
        media_lookup=lookup,
        uow_factory=MagicMock(return_value=uow),
        processor=processor,
        ocr_service=ocr,
        config=_config(languages),
    )


_COMPLETED = FileOcrReport(
    outcome=SubtitleOcrOutcome.COMPLETED,
    image_track_count=1,
    track_results=[
        SubtitleTrackOcrResult(
            track_index=0, language="pt", outcome=SubtitleTrackOutcome.EXTRACTED, cue_count=42
        )
    ],
)


@pytest.mark.unit
@pytest.mark.asyncio
class TestRunSubtitleOcrForMedia:
    async def test_movie_ocr_records_completed_run_and_marker(self, tmp_path: Path) -> None:
        path = tmp_path / "m.mkv"
        lookup = _lookup(
            movie_source=MediaSourceInfo(
                media_id="mov_cccccccccccc", title="Nausicaa", file_path=str(path)
            )
        )
        proc = _processor(_COMPLETED)
        use_case = _use_case(lookup, _uow(), proc, _ocr_service())

        out = await use_case.execute(
            RunSubtitleOcrInput(media_kind="movie", media_id="mov_cccccccccccc")
        )

        assert out.media_kind == "movie"
        assert out.media_title == "Nausicaa"
        assert out.outcome == SubtitleOcrOutcome.COMPLETED.value
        assert out.extracted_count == 1
        assert out.track_results[0].cue_count == 42
        # empty config languages -> no filter (every mappable track)
        assert proc.process_file.call_args.args[3] is None

    async def test_honours_configured_languages(self, tmp_path: Path) -> None:
        path = tmp_path / "m.mkv"
        lookup = _lookup(
            movie_source=MediaSourceInfo(
                media_id="mov_cccccccccccc", title="Nausicaa", file_path=str(path)
            )
        )
        proc = _processor(_COMPLETED)
        # a 20+ track remux must not OCR everything — scope by config
        use_case = _use_case(lookup, _uow(), proc, _ocr_service(), languages=("pt", "en"))

        await use_case.execute(RunSubtitleOcrInput(media_kind="movie", media_id="mov_cccccccccccc"))

        assert proc.process_file.call_args.args[3] == frozenset({"pt", "en"})
        # COMPLETED writes the done marker
        assert (ocr_subtitle_output_dir(path, ".homeflix/subtitles") / OCR_DONE_MARKER).exists()

    async def test_tesseract_unavailable_records_failed_run(self, tmp_path: Path) -> None:
        path = tmp_path / "m.mkv"
        lookup = _lookup(
            movie_source=MediaSourceInfo(
                media_id="mov_aaaaaaaaaaaa", title="Nausicaa", file_path=str(path)
            )
        )
        proc = _processor(_COMPLETED)
        use_case = _use_case(lookup, _uow(), proc, _ocr_service(langs=frozenset()))

        out = await use_case.execute(
            RunSubtitleOcrInput(media_kind="movie", media_id="mov_aaaaaaaaaaaa")
        )

        assert out.outcome == SubtitleOcrOutcome.FAILED.value
        assert out.error is not None
        proc.process_file.assert_not_called()
        # FAILED does not write the done marker (so it can be retried)
        assert not (ocr_subtitle_output_dir(path, ".homeflix/subtitles") / OCR_DONE_MARKER).exists()

    async def test_movie_not_found_raises(self, tmp_path: Path) -> None:
        lookup = _lookup(movie_source=None)
        use_case = _use_case(lookup, _uow(), _processor(_COMPLETED), _ocr_service())

        with pytest.raises(ResourceNotFoundException):
            await use_case.execute(
                RunSubtitleOcrInput(media_kind="movie", media_id="mov_dddddddddddd")
            )

    async def test_episode_ocr_uses_series_label(self, tmp_path: Path) -> None:
        path = tmp_path / "e.mkv"
        lookup = _lookup(
            episode_source=MediaSourceInfo(
                media_id="epi_eeeeeeeeeeee", title="Show S01E03", file_path=str(path)
            )
        )
        use_case = _use_case(lookup, _uow(), _processor(_COMPLETED), _ocr_service())

        out = await use_case.execute(
            RunSubtitleOcrInput(media_kind="episode", media_id="epi_eeeeeeeeeeee")
        )

        assert out.media_kind == "episode"
        assert out.media_title == "Show S01E03"

    async def test_unknown_kind_raises(self, tmp_path: Path) -> None:
        use_case = _use_case(_lookup(), _uow(), _processor(_COMPLETED), _ocr_service())

        with pytest.raises(ValueError, match="Unknown media_kind"):
            await use_case.execute(
                RunSubtitleOcrInput(media_kind="bogus", media_id="mov_ffffffffffff")
            )
