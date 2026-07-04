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
from src.modules.media.application.dtos.subtitle_ocr_run_dtos import (
    RunSubtitleOcrInput,
    SubtitleOcrRunOutput,
    subtitle_ocr_run_to_output,
)
from src.modules.media.application.ports.subtitle_ocr_port import SubtitleOcrOptions
from src.modules.media.application.services.subtitle_ocr_paths import (
    OCR_DONE_MARKER,
    ocr_subtitle_output_dir,
)
from src.modules.media.application.services.subtitle_ocr_processor import FileOcrReport
from src.modules.media.domain.entities.subtitle_ocr_run import SubtitleOcrRun
from src.modules.media.domain.value_objects import EpisodeId, MovieId
from src.modules.media.domain.value_objects.subtitle_ocr_outcome import SubtitleOcrOutcome

if TYPE_CHECKING:
    from src.modules.media.application.ports.runtime_config_ports import (
        SubtitleOcrRunConfigPort,
    )
    from src.modules.media.application.ports.subtitle_ocr_port import SubtitleOcrPort
    from src.modules.media.application.services.subtitle_ocr_processor import (
        SubtitleOcrProcessor,
    )
    from src.modules.media.application.unit_of_work import MediaUnitOfWorkFactory

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
        media_uow_factory: Loads the entity and records the run.
        processor: Shared OCR-one-file service.
        ocr_service: Used to check tesseract availability up front.
        config: Async access to the subtitle-OCR + streaming config.
    """

    def __init__(
        self,
        media_uow_factory: MediaUnitOfWorkFactory,
        processor: SubtitleOcrProcessor,
        ocr_service: SubtitleOcrPort,
        config: SubtitleOcrRunConfigPort,
    ) -> None:
        self._media_uow_factory = media_uow_factory
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
            return await self._resolve_movie(input_dto.media_id)
        if input_dto.media_kind == _EPISODE:
            return await self._resolve_episode(input_dto.media_id)
        msg = f"Unknown media_kind: {input_dto.media_kind!r}"
        raise ValueError(msg)

    async def _resolve_movie(self, media_id: str) -> _MediaRef:
        async with self._media_uow_factory() as uow:
            movie = await uow.movies.find_by_id(MovieId(media_id))
        if movie is None or movie.primary_file is None:
            raise ResourceNotFoundException.for_resource("Movie", media_id)
        return _MediaRef(
            kind=_MOVIE,
            media_id=str(movie.id),
            title=movie.title.value,
            path=Path(movie.primary_file.file_path.value),
        )

    async def _resolve_episode(self, media_id: str) -> _MediaRef:
        async with self._media_uow_factory() as uow:
            series = await uow.series.find_by_episode_id(EpisodeId(media_id))
        episode = None
        if series is not None:
            episode = next(
                (
                    e
                    for season in series.seasons
                    for e in season.episodes
                    if e.id is not None and str(e.id) == media_id
                ),
                None,
            )
        if series is None or episode is None or episode.primary_file is None:
            raise ResourceNotFoundException.for_resource("Episode", media_id)
        label = (
            f"{series.title.value} "
            f"S{episode.season_number.value:02d}E{episode.episode_number.value:02d}"
        )
        return _MediaRef(
            kind=_EPISODE,
            media_id=str(episode.id),
            title=label,
            path=Path(episode.primary_file.file_path.value),
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
        async with self._media_uow_factory() as uow:
            saved = await uow.subtitle_ocr_runs.add(run)
        return subtitle_ocr_run_to_output(saved)

    @staticmethod
    def _write_marker(output_dir: Path) -> None:
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / OCR_DONE_MARKER).write_text("", encoding="utf-8")


__all__ = ["RunSubtitleOcrForMediaUseCase"]
