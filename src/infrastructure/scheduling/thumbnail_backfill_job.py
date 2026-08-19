"""Periodic backfill of scrub-preview thumbnails.

Generates sprite + WebVTT scrub previews for movies and episodes that
do not have one yet and persists the path back to the entity. The job
runs on an APScheduler interval so the catalog converges to "every
file has thumbnails" without any user interaction; new items added by
a scan are picked up on the next tick.

Each tick processes at most ``batch_size`` items split between movies
and episodes, keeping CPU usage bounded on large catalogs.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING

from src.config.logging import get_logger
from src.modules.media.domain.value_objects import EpisodeId, ImageUrl, MovieId
from src.modules.streaming.infrastructure.streaming.thumbnail_service import (
    ThumbnailGenerationService,
    ThumbnailResult,
    scrub_preview_output_dir,
)

if TYPE_CHECKING:
    from src.modules.media.application.unit_of_work import MediaUnitOfWorkFactory
    from src.modules.media.domain.entities import Episode, Movie
    from src.modules.settings.infrastructure.runtime_settings import RuntimeSettings

_logger = get_logger()


class ThumbnailBackfillJob:
    """Generate scrub-preview thumbnails for media missing them.

    Splits the per-tick budget between movies and episodes: movies are
    processed first, and any remaining slots go to episodes. A series
    of ticks therefore grinds through the movie backlog before
    starting on episodes — acceptable because both eventually drain
    and operators rarely have a million of either.

    All operator-tunable knobs (``batch_size``, sprite ``subdir``)
    are read from :class:`RuntimeSettings` per ``run()`` so admin
    edits propagate to the next tick without restart (ADR-013). The
    on-demand ``process_movie``/``process_episode`` entry points
    (eager triggers from the HLS route) read the snapshot lazily on
    each invocation for the same reason.

    Args:
        media_uow_factory: Builds fresh media UoWs per tick. The job
            opens its own UoW per item so a single failure rolls back
            only that item's update, not the whole batch.
        runtime_settings: Snapshot facade for
            :class:`ThumbnailBackfillConfig`.
        thumbnail_service: Sprite + VTT generator. Default constructs
            its own; tests inject a fake.
    """

    def __init__(
        self,
        media_uow_factory: MediaUnitOfWorkFactory,
        runtime_settings: RuntimeSettings,
        thumbnail_service: ThumbnailGenerationService | None = None,
    ) -> None:
        self._media_uow_factory = media_uow_factory
        self._runtime_settings = runtime_settings
        self._thumbnail_service = thumbnail_service or ThumbnailGenerationService(
            runtime_settings=runtime_settings,
        )
        # Guard for the eager (fire-and-forget) trigger fired per HLS
        # playlist request. Without it, an HLS remount (resume bucket,
        # skip-intro re-anchor) or a replay re-fires generation for the
        # *same* still-preview-less file, and several whole-file NVDEC
        # sprite decodes stack up and peg the GPU. ``_eager_inflight``
        # de-dups by media key; ``_eager_gate`` + ``_eager_active`` bound
        # how many distinct files generate at once (``eager_concurrency``
        # from settings — re-read per slot so admin edits apply live).
        # The periodic ``run()`` is already sequential and ignores this.
        self._eager_inflight: set[str] = set()
        self._eager_active = 0
        self._eager_gate = asyncio.Condition()

    async def _eager_limit(self) -> int:
        """Current max parallel eager generations (from settings)."""
        return (await self._runtime_settings.thumbnail_backfill()).eager_concurrency

    async def _acquire_eager_slot(self) -> None:
        """Block until an eager generation slot is free, then claim it."""
        async with self._eager_gate:
            while self._eager_active >= await self._eager_limit():
                await self._eager_gate.wait()
            self._eager_active += 1

    async def _release_eager_slot(self) -> None:
        """Release a slot and wake one waiter."""
        async with self._eager_gate:
            self._eager_active = max(0, self._eager_active - 1)
            self._eager_gate.notify(1)

    async def run(self) -> None:
        """Process one batch of missing thumbnails.

        Counts processed items toward the shared budget so the tick
        never exceeds ``batch_size`` even if both queues are non-empty.
        Logged metrics: how many of each type were generated and how
        many were skipped (because the source file vanished or ffmpeg
        could not produce a sprite).
        """
        config = await self._runtime_settings.thumbnail_backfill()
        budget = config.batch_size

        movies = await self._fetch_missing_movies(budget)
        movies_done, movies_skipped = await self._process_movies(movies, config.subdir)
        budget -= len(movies)

        episodes_done = 0
        episodes_skipped = 0
        if budget > 0:
            episodes = await self._fetch_missing_episodes(budget)
            episodes_done, episodes_skipped = await self._process_episodes(episodes, config.subdir)

        if movies_done or movies_skipped or episodes_done or episodes_skipped:
            _logger.info(
                "[thumbnail-backfill] tick complete",
                movies_done=movies_done,
                movies_skipped=movies_skipped,
                episodes_done=episodes_done,
                episodes_skipped=episodes_skipped,
                batch_size=config.batch_size,
            )

    async def _fetch_missing_movies(self, limit: int) -> list[Movie]:
        async with self._media_uow_factory() as uow:
            return list(await uow.movies.find_missing_scrub_preview(limit))

    async def _fetch_missing_episodes(self, limit: int) -> list[Episode]:
        async with self._media_uow_factory() as uow:
            return list(await uow.series.find_episodes_missing_scrub_preview(limit))

    async def process_movie_by_id(self, movie_id: str) -> bool:
        """Eager-trigger entry point: fetch the movie then generate.

        Loads the entity in a short-lived UoW so the caller (typically a
        fire-and-forget ``asyncio.create_task`` on the HLS playlist
        route) can hand off just the id and never owns a DB session.
        Re-checks ``scrub_preview_path`` on the freshly-loaded entity
        to avoid a redundant ffmpeg run if another tick already filled
        it in between request and dispatch.

        Single-flighted + concurrency-capped (see ``__init__``): a repeat
        eager fire for a movie already generating is dropped, and distinct
        movies queue on the semaphore instead of all decoding at once.
        """
        key = f"mov:{movie_id}"
        if key in self._eager_inflight:
            return False
        self._eager_inflight.add(key)
        try:
            async with self._media_uow_factory() as uow:
                movie = await uow.movies.find_by_id(MovieId(movie_id))
            if movie is None or movie.scrub_preview_path is not None:
                return False
            subdir = (await self._runtime_settings.thumbnail_backfill()).subdir
            await self._acquire_eager_slot()
            try:
                return await self.process_movie(movie, subdir)
            finally:
                await self._release_eager_slot()
        finally:
            self._eager_inflight.discard(key)

    async def process_episode_by_id(self, episode_id: str) -> bool:
        """Eager-trigger entry point for episodes — see ``process_movie_by_id``."""
        key = f"epi:{episode_id}"
        if key in self._eager_inflight:
            return False
        self._eager_inflight.add(key)
        try:
            async with self._media_uow_factory() as uow:
                episode = await uow.series.find_episode_by_id(EpisodeId(episode_id))
            if episode is None or episode.scrub_preview_path is not None:
                return False
            subdir = (await self._runtime_settings.thumbnail_backfill()).subdir
            await self._acquire_eager_slot()
            try:
                return await self.process_episode(episode, subdir)
            finally:
                await self._release_eager_slot()
        finally:
            self._eager_inflight.discard(key)

    async def process_movie(self, movie: Movie, subdir: str) -> bool:
        """Generate and persist scrub-preview thumbnails for a single movie.

        Reusable by both the periodic batch and the eager trigger fired
        from the HLS playlist route. Logs the failure reason internally
        and degrades to ``False`` rather than raising — the caller is
        usually fire-and-forget and cannot meaningfully react.

        Returns:
            ``True`` if a sprite + VTT were produced and the path was
            persisted; ``False`` if the source file was missing, the
            entity had no primary file, or ffmpeg could not produce a
            sprite.
        """
        file_path = self._primary_file_path(movie)
        if file_path is None:
            return False
        result = await self._generate(file_path, subdir)
        if result is None:
            return False
        await self._persist_movie(movie, result)
        return True

    async def process_episode(self, episode: Episode, subdir: str) -> bool:
        """Generate and persist scrub-preview thumbnails for a single episode.

        Mirror of ``process_movie`` for episodes. Skips silently if the
        episode has no primary file or no id (a freshly-built entity
        that was never persisted).
        """
        file_path = self._primary_file_path(episode)
        if file_path is None or episode.id is None:
            return False
        result = await self._generate(file_path, subdir)
        if result is None:
            return False
        await self._persist_episode(episode, result)
        return True

    async def _process_movies(self, movies: list[Movie], subdir: str) -> tuple[int, int]:
        done = 0
        skipped = 0
        for movie in movies:
            if await self.process_movie(movie, subdir):
                done += 1
            else:
                skipped += 1
        return done, skipped

    async def _process_episodes(self, episodes: list[Episode], subdir: str) -> tuple[int, int]:
        done = 0
        skipped = 0
        for episode in episodes:
            if await self.process_episode(episode, subdir):
                done += 1
            else:
                skipped += 1
        return done, skipped

    @staticmethod
    def _primary_file_path(entity: Movie | Episode) -> str | None:
        primary = entity.primary_file
        if primary is None:
            return None
        return primary.file_path.value

    async def _generate(self, file_path: str, subdir: str) -> ThumbnailResult | None:
        """Run sprite generation off the event loop and return its result.

        ``ThumbnailGenerationService.generate`` is fully synchronous
        (subprocess.run + filesystem writes) so calling it on the event
        loop would block FastAPI. ``asyncio.to_thread`` defers it to
        the default executor, which is what every other CPU-bound bit
        of streaming work in this codebase already uses.
        """
        source = Path(file_path)
        if not source.is_file():
            _logger.debug(
                "[thumbnail-backfill] source missing on disk; skipping",
                file_path=file_path,
            )
            return None
        output_dir = scrub_preview_output_dir(source, subdir)
        return await asyncio.to_thread(
            self._thumbnail_service.generate,
            file_path,
            output_dir,
        )

    async def _persist_movie(self, movie: Movie, result: ThumbnailResult) -> None:
        path_value = ImageUrl(str(result.vtt_path))
        async with self._media_uow_factory() as uow:
            await uow.movies.save(movie.with_updates(scrub_preview_path=path_value))

    async def _persist_episode(self, episode: Episode, result: ThumbnailResult) -> None:
        if episode.id is None:
            raise RuntimeError("Episode loaded from repository has no id")
        async with self._media_uow_factory() as uow:
            await uow.series.update_episode_scrub_preview_path(
                episode.id,
                str(result.vtt_path),
            )


__all__ = ["ThumbnailBackfillJob"]
