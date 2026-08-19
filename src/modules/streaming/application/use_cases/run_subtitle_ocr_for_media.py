"""RunSubtitleOcrForMediaUseCase — manual "OCR this title now" trigger.

Runs the OCR pipeline on a single movie/episode on demand, records an
audit run, and returns it. Unlike the periodic job it ignores the
per-file ``.ocr_done`` marker (it always re-processes), but it *does*
honour the operator's ``languages`` allow-list — some Blu-ray remuxes
carry 20+ PGS tracks, and OCR-ing every one would take hours, so the
scope is bounded by the configured languages (empty = every mappable
track). It does not require the periodic job to be enabled — but it does
need tesseract on the host.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from src.building_blocks.application.errors import ResourceNotFoundException
from src.config.logging import get_logger
from src.modules.streaming.application.dtos.subtitle_ocr_run_dtos import (
    RunSubtitleOcrInput,
    SubtitleOcrRunOutput,
    subtitle_ocr_run_to_output,
)
from src.modules.streaming.application.ports.subtitle_ocr_port import SubtitleOcrOptions
from src.modules.streaming.application.services.subtitle_ocr_paths import (
    OCR_DONE_MARKER,
    ocr_subtitle_output_dir,
)
from src.modules.streaming.application.services.subtitle_ocr_processor import FileOcrReport
from src.modules.streaming.domain.entities.subtitle_ocr_run import SubtitleOcrRun
from src.modules.streaming.domain.value_objects.subtitle_ocr_outcome import SubtitleOcrOutcome

if TYPE_CHECKING:
    from src.modules.streaming.application.ports.media_lookup_port import (
        MediaPlaybackLookupPort,
        MediaSourceInfo,
    )
    from src.modules.streaming.application.ports.runtime_config_ports import (
        SubtitleOcrRunConfigPort,
    )
    from src.modules.streaming.application.ports.subtitle_ocr_port import SubtitleOcrPort
    from src.modules.streaming.application.services.subtitle_ocr_processor import (
        SubtitleOcrProcessor,
    )
    from src.modules.streaming.application.unit_of_work import StreamingUnitOfWorkFactory

_logger = get_logger()

_MOVIE = "movie"
_EPISODE = "episode"


@dataclass(frozen=True)
class _MediaRef:
    kind: str
    media_id: str
    title: str
    path: Path


class RunSubtitleOcrForMediaUseCase:
    """OCR one movie/episode on demand and record the run.

    Args:
        media_lookup: Operator-scoped catalog lookup that resolves the
            source file + title for a movie/episode (no per-profile ACL —
            OCR is admin-only).
        uow_factory: Opens a streaming Unit of Work to record the run.
        processor: Shared OCR-one-file service.
        ocr_service: Used to check tesseract availability up front.
        config: Async access to the subtitle-OCR + streaming config.
    """

    def __init__(
        self,
        media_lookup: MediaPlaybackLookupPort,
        uow_factory: StreamingUnitOfWorkFactory,
        processor: SubtitleOcrProcessor,
        ocr_service: SubtitleOcrPort,
        config: SubtitleOcrRunConfigPort,
    ) -> None:
        self._media_lookup = media_lookup
        self._uow_factory = uow_factory
        self._processor = processor
        self._ocr_service = ocr_service
        self._config = config

    async def execute(self, input_dto: RunSubtitleOcrInput) -> SubtitleOcrRunOutput:
        """Run OCR for the given media and return the recorded run.

        Raises:
            ResourceNotFoundException: If the movie/episode does not exist
                or has no primary file.
            ValueError: If ``media_kind`` is neither ``movie`` nor
                ``episode``.
        """
        ref = await self._resolve(input_dto)
        config = await self._config.subtitle_ocr()
        started_at = datetime.now(UTC)

        if not self._ocr_service.available_languages(config.tesseract_binary):
            return await self._record(
                ref,
                FileOcrReport(outcome=SubtitleOcrOutcome.FAILED),
                "No tesseract language models installed on the host",
                started_at,
            )

        streaming = await self._config.streaming()
        options = SubtitleOcrOptions(
            tesseract_binary=config.tesseract_binary,
            per_cue_timeout_seconds=config.per_cue_timeout_seconds,
            ffmpeg_threads=streaming.ffmpeg_threads,
        )
        output_dir = ocr_subtitle_output_dir(ref.path, config.subdir)
        # Honour the configured languages so a 20+ track remux doesn't OCR
        # everything; empty means every mappable track.
        language_filter = frozenset(lang.lower() for lang in config.languages) or None

        error: str | None = None
        try:
            report = await asyncio.to_thread(
                self._processor.process_file,
                str(ref.path),
                output_dir,
                options,
                language_filter,
            )
        except Exception as exc:  # — surface as a FAILED run, not a 500
            _logger.exception("[subtitle-ocr] manual run failed", extra={"source": str(ref.path)})
            report = FileOcrReport(outcome=SubtitleOcrOutcome.FAILED)
            error = f"{type(exc).__name__}: {exc}"[:2000]

        if report.outcome == SubtitleOcrOutcome.COMPLETED:
            self._write_marker(output_dir)
        return await self._record(ref, report, error, started_at)

    async def _resolve(self, input_dto: RunSubtitleOcrInput) -> _MediaRef:
        if input_dto.media_kind == _MOVIE:
            source = await self._media_lookup.find_movie_source(input_dto.media_id)
            return self._to_ref(_MOVIE, "Movie", input_dto.media_id, source)
        if input_dto.media_kind == _EPISODE:
            source = await self._media_lookup.find_episode_source(input_dto.media_id)
            return self._to_ref(_EPISODE, "Episode", input_dto.media_id, source)
        msg = f"Unknown media_kind: {input_dto.media_kind!r}"
        raise ValueError(msg)

    @staticmethod
    def _to_ref(
        kind: str,
        resource: str,
        media_id: str,
        source: MediaSourceInfo | None,
    ) -> _MediaRef:
        if source is None or source.file_path is None:
            raise ResourceNotFoundException.for_resource(resource, media_id)
        return _MediaRef(
            kind=kind,
            media_id=source.media_id,
            title=source.title,
            path=Path(source.file_path),
        )

    async def _record(
        self,
        ref: _MediaRef,
        report: FileOcrReport,
        error: str | None,
        started_at: datetime,
    ) -> SubtitleOcrRunOutput:
        run = SubtitleOcrRun(
            media_kind=ref.kind,
            media_id=ref.media_id,
            media_title=ref.title,
            file_path=str(ref.path),
            outcome=report.outcome,
            image_track_count=report.image_track_count,
            extracted_count=report.extracted_count,
            track_results=report.track_results,
            error=error,
            started_at=started_at,
            finished_at=datetime.now(UTC),
        )
        async with self._uow_factory() as uow:
            saved = await uow.subtitle_ocr_runs.add(run)
        return subtitle_ocr_run_to_output(saved)

    @staticmethod
    def _write_marker(output_dir: Path) -> None:
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / OCR_DONE_MARKER).write_text("", encoding="utf-8")


__all__ = ["RunSubtitleOcrForMediaUseCase"]
