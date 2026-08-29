"""Tests for the subtitle-OCR run (audit) use cases."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.building_blocks.application.errors import ResourceNotFoundException
from src.modules.streaming.application.dtos.subtitle_ocr_run_dtos import (
    GetSubtitleOcrRunInput,
    ListSubtitleOcrRunsInput,
)
from src.modules.streaming.application.use_cases.get_subtitle_ocr_run import (
    GetSubtitleOcrRunUseCase,
)
from src.modules.streaming.application.use_cases.list_subtitle_ocr_runs import (
    ListSubtitleOcrRunsUseCase,
)
from src.modules.streaming.domain.entities.subtitle_ocr_run import (
    SubtitleOcrRun,
    SubtitleTrackOcrResult,
)
from src.modules.streaming.domain.value_objects.subtitle_ocr_outcome import (
    SubtitleOcrOutcome,
    SubtitleTrackOutcome,
)
from src.modules.streaming.domain.value_objects.subtitle_ocr_run_id import SubtitleOcrRunId


def _run() -> SubtitleOcrRun:
    now = datetime(2026, 7, 4, 12, 0, tzinfo=UTC)
    return SubtitleOcrRun(
        id=SubtitleOcrRunId.generate(),
        media_kind="movie",
        media_id="mov_test00000001",
        media_title="Nausicaa",
        file_path="G:/movies/nausicaa.mkv",
        outcome=SubtitleOcrOutcome.COMPLETED,
        image_track_count=2,
        extracted_count=1,
        track_results=[
            SubtitleTrackOcrResult(
                track_index=0,
                language="en",
                outcome=SubtitleTrackOutcome.EXTRACTED,
                cue_count=1079,
            ),
        ],
        started_at=now,
        finished_at=now,
    )


def _uow(
    *, runs: list[SubtitleOcrRun] | None = None, found: SubtitleOcrRun | None = None
) -> AsyncMock:
    uow = AsyncMock()
    uow.__aenter__.return_value = uow
    uow.__aexit__.return_value = None
    uow.subtitle_ocr_runs = AsyncMock()
    uow.subtitle_ocr_runs.list_paginated = AsyncMock(return_value=runs or [])
    uow.subtitle_ocr_runs.find_by_id = AsyncMock(return_value=found)
    return uow


@pytest.mark.unit
class TestSubtitleOcrRunUseCases:
    @pytest.mark.asyncio
    async def test_list_projects_runs_to_output(self) -> None:
        run = _run()
        uow = _uow(runs=[run])
        use_case = ListSubtitleOcrRunsUseCase(uow_factory=MagicMock(return_value=uow))

        rows = await use_case.execute(ListSubtitleOcrRunsInput(media_kind="movie"))

        assert len(rows) == 1
        assert rows[0].id == str(run.id)
        assert rows[0].outcome == SubtitleOcrOutcome.COMPLETED.value
        assert rows[0].extracted_count == 1
        assert rows[0].track_results[0].outcome == SubtitleTrackOutcome.EXTRACTED.value
        assert rows[0].track_results[0].cue_count == 1079
        uow.subtitle_ocr_runs.list_paginated.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_returns_run_when_found(self) -> None:
        run = _run()
        uow = _uow(found=run)
        use_case = GetSubtitleOcrRunUseCase(uow_factory=MagicMock(return_value=uow))

        output = await use_case.execute(GetSubtitleOcrRunInput(run_id=str(run.id)))

        assert output.id == str(run.id)
        assert output.media_title == "Nausicaa"
        assert output.image_track_count == 2

    @pytest.mark.asyncio
    async def test_get_raises_when_not_found(self) -> None:
        uow = _uow(found=None)
        use_case = GetSubtitleOcrRunUseCase(uow_factory=MagicMock(return_value=uow))

        with pytest.raises(ResourceNotFoundException):
            await use_case.execute(GetSubtitleOcrRunInput(run_id=str(SubtitleOcrRunId.generate())))
