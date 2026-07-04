"""Periodic backfill of OCR text sidecars for image-based subtitles.

For each movie/episode that has not been processed yet, probes the file
for image-based subtitle tracks (PGS/SUP) and OCRs each into a text
WebVTT sidecar (ADR-027). Once a file's OCR sidecars exist, the probe
surfaces them as selectable text subtitles (see
``subtitle_ocr_surfacing``); the catalog therefore converges to "every
PGS subtitle has a text sibling" without any user interaction.

Work discovery is a per-file ``.ocr_done`` marker on disk, not a DB
column: subtitle tracks are not persisted, so there is no cheap SQL
predicate. The marker means "attempted" — it is written whenever a file
is processed under a functioning tesseract, so a genuinely unusable
track (e.g. VOBSUB) does not block the queue. To reprocess a file (after
installing a new language model, say), delete its marker.

If tesseract has no language models installed, the whole tick is skipped
and no markers are written, so nothing is silently marked done while OCR
is non-functional.

Each tick processes at most ``batch_size`` files (movies first, then
episodes) to keep CPU bounded — OCR is expensive.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING

from src.config.logging import get_logger
from src.modules.media.application.ports.subtitle_ocr_port import SubtitleOcrOptions
from src.modules.media.infrastructure.streaming.subtitle_ocr_service import (
    ocr_subtitle_output_dir,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

    from src.modules.media.application.ports.media_probe_port import MediaProbePort
    from src.modules.media.application.ports.subtitle_ocr_port import SubtitleOcrPort
    from src.modules.media.application.unit_of_work import MediaUnitOfWorkFactory
    from src.modules.media.domain.entities import Episode, Movie
    from src.modules.settings.domain.value_objects import SubtitleOcrConfig
    from src.modules.settings.infrastructure.runtime_settings import RuntimeSettings

_logger = get_logger()

#: Sentinel written into a file's OCR output dir once it has been
#: processed, so subsequent ticks skip it without re-probing.
OCR_DONE_MARKER = ".ocr_done"


class SubtitleOcrBackfillJob:
    """OCR image-based subtitles to text sidecars for media missing them.

    Movies are processed before episodes within the shared per-tick
    budget, so a series of ticks grinds through the movie backlog first.
    All knobs (``batch_size``, ``subdir``, ``languages``,
    ``tesseract_binary``, ``per_cue_timeout_seconds``) are read from
    :class:`RuntimeSettings` per ``run()`` so admin edits propagate to
    the next tick without restart (ADR-013).

    Args:
        media_uow_factory: Builds fresh media UoWs per query. The job
            opens a short-lived UoW to list media, then does OCR (slow,
            off-session) without holding a DB session.
        runtime_settings: Snapshot facade for :class:`SubtitleOcrConfig`
            (and streaming ``ffmpeg_threads``).
        ocr_service: The OCR engine (:class:`SubtitleOcrPort`).
        probe_service: Discovers each file's subtitle tracks.
    """

    def __init__(
        self,
        media_uow_factory: MediaUnitOfWorkFactory,
        runtime_settings: RuntimeSettings,
        ocr_service: SubtitleOcrPort,
        probe_service: MediaProbePort,
    ) -> None:
        self._media_uow_factory = media_uow_factory
        self._runtime_settings = runtime_settings
        self._ocr_service = ocr_service
        self._probe = probe_service

    async def run(self) -> None:
        """Process one batch of media missing OCR sidecars."""
        config = await self._runtime_settings.subtitle_ocr()
        if not config.enabled:
            return

        available = self._ocr_service.available_languages(config.tesseract_binary)
        if not available:
            _logger.warning("[subtitle-ocr] no tesseract languages installed; skipping tick")
            return

        streaming = await self._runtime_settings.streaming()
        options = SubtitleOcrOptions(
            tesseract_binary=config.tesseract_binary,
            per_cue_timeout_seconds=config.per_cue_timeout_seconds,
            ffmpeg_threads=streaming.ffmpeg_threads,
        )

        budget = config.batch_size
        movies = await self._unprocessed_movie_files(config.subdir, budget)
        for source in movies:
            await self._process_file(source, config, options)

        episodes_done = 0
        budget -= len(movies)
        if budget > 0:
            episodes = await self._unprocessed_episode_files(config.subdir, budget)
            for source in episodes:
                await self._process_file(source, config, options)
            episodes_done = len(episodes)

        if movies or episodes_done:
            _logger.info(
                "[subtitle-ocr] tick complete",
                movies=len(movies),
                episodes=episodes_done,
                batch_size=config.batch_size,
            )

    async def _unprocessed_movie_files(self, subdir: str, limit: int) -> list[Path]:
        async with self._media_uow_factory() as uow:
            movies = await uow.movies.list_all()
        return self._collect_unprocessed((self._primary_path(m) for m in movies), subdir, limit)

    async def _unprocessed_episode_files(self, subdir: str, limit: int) -> list[Path]:
        async with self._media_uow_factory() as uow:
            series = await uow.series.list_all()
        episodes = (
            self._primary_path(episode)
            for s in series
            for season in s.seasons
            for episode in season.episodes
        )
        return self._collect_unprocessed(episodes, subdir, limit)

    @staticmethod
    def _collect_unprocessed(sources: Iterable[Path | None], subdir: str, limit: int) -> list[Path]:
        """Take the first ``limit`` on-disk files that lack a done marker."""
        out: list[Path] = []
        for source in sources:
            if source is None or not source.is_file():
                continue
            if (ocr_subtitle_output_dir(source, subdir) / OCR_DONE_MARKER).exists():
                continue
            out.append(source)
            if len(out) >= limit:
                break
        return out

    @staticmethod
    def _primary_path(entity: Movie | Episode) -> Path | None:
        primary = entity.primary_file
        if primary is None:
            return None
        return Path(primary.file_path.value)

    async def _process_file(
        self,
        source: Path,
        config: SubtitleOcrConfig,
        options: SubtitleOcrOptions,
    ) -> None:
        """OCR a single file's image subtitles, then mark it processed.

        Runs off the event loop (probe + OCR are synchronous, CPU/IO
        bound). Best-effort: any failure is logged and the file is still
        marked processed (the marker means "attempted"), so one bad file
        never wedges the queue — the operator deletes the marker to retry.
        """
        try:
            await asyncio.to_thread(self._ocr_file, source, config, options)
        except Exception:
            _logger.exception(
                "[subtitle-ocr] failed to process file", extra={"source": str(source)}
            )
        self._write_marker(source, config.subdir)

    def _ocr_file(
        self,
        source: Path,
        config: SubtitleOcrConfig,
        options: SubtitleOcrOptions,
    ) -> None:
        """Probe ``source`` and OCR each image subtitle track (sync)."""
        probe = self._probe.probe(str(source))
        image_tracks = [t for t in probe.all_subtitles if t.is_image_based]
        wanted = _language_filter(config.languages)
        output_dir = ocr_subtitle_output_dir(source, config.subdir)
        for track in image_tracks:
            if wanted is not None and track.language.value.lower() not in wanted:
                continue
            self._ocr_service.ocr_track(str(source), track, output_dir, options)

    @staticmethod
    def _write_marker(source: Path, subdir: str) -> None:
        output_dir = ocr_subtitle_output_dir(source, subdir)
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / OCR_DONE_MARKER).write_text("", encoding="utf-8")


def _language_filter(languages: tuple[str, ...]) -> frozenset[str] | None:
    """Return the lowercased ISO allow-set, or None for 'all languages'."""
    if not languages:
        return None
    return frozenset(lang.lower() for lang in languages)


__all__ = ["OCR_DONE_MARKER", "SubtitleOcrBackfillJob"]
