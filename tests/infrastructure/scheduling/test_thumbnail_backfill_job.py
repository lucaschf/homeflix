"""Tests for ThumbnailBackfillJob.

Stubs the media UoW factory and the thumbnail service so the tests
exercise the job's orchestration (budget split, persistence path,
skip-when-source-missing) without touching the database or ffmpeg.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.infrastructure.scheduling.thumbnail_backfill_job import ThumbnailBackfillJob
from src.modules.media.domain.entities import Episode, Movie
from src.modules.media.domain.value_objects import (
    Duration,
    EpisodeId,
    EpisodeNumber,
    FilePath,
    ImageUrl,
    MediaFile,
    Resolution,
    SeasonNumber,
    SeriesId,
    Title,
)
from src.modules.media.infrastructure.streaming.thumbnail_service import ThumbnailResult
from src.modules.settings.domain.value_objects import ThumbnailBackfillConfig

if TYPE_CHECKING:
    from pathlib import Path

_LIBRARY_ID = "lib_test12345678"


def _make_movie(file_path: str = "/media/movies/inception/inception.mkv") -> Movie:
    return Movie.create(
        library_id=_LIBRARY_ID,
        title="Inception",
        year=2010,
        duration=8880,
        file_path=file_path,
        file_size=4_000_000_000,
        resolution="1080p",
    )


def _make_episode(file_path: str = "/media/series/show/s01e01.mkv") -> Episode:
    return Episode(
        id=EpisodeId.generate(),
        series_id=SeriesId.generate(),
        season_number=SeasonNumber(1),
        episode_number=EpisodeNumber(1),
        title=Title("Pilot"),
        duration=Duration(2700),
        files=[
            MediaFile(
                file_path=FilePath(file_path),
                file_size=1_000_000_000,
                resolution=Resolution("1080p"),
                is_primary=True,
            ),
        ],
    )


def _build_uow(
    *,
    movies_missing: list[Movie],
    episodes_missing: list[Episode],
    movie_by_id: Movie | None = None,
    episode_by_id: Episode | None = None,
) -> AsyncMock:
    """Build a UoW whose movie/series repos return the supplied collections."""
    uow = AsyncMock()
    uow.__aenter__.return_value = uow
    uow.__aexit__.return_value = None
    uow.movies = AsyncMock()
    uow.movies.find_missing_scrub_preview = AsyncMock(return_value=movies_missing)
    uow.movies.find_by_id = AsyncMock(return_value=movie_by_id)
    uow.movies.save = AsyncMock(side_effect=lambda m: m)
    uow.series = AsyncMock()
    uow.series.find_episodes_missing_scrub_preview = AsyncMock(return_value=episodes_missing)
    uow.series.find_episode_by_id = AsyncMock(return_value=episode_by_id)
    uow.series.update_episode_scrub_preview_path = AsyncMock(return_value=True)
    return uow


def _make_thumbnail_service(vtt_path: Path) -> MagicMock:
    """Stub thumbnail service that always returns a fixed VTT path."""
    service = MagicMock()
    service.generate.return_value = ThumbnailResult(
        sprite_path=vtt_path.with_name("sprite.jpg"),
        vtt_path=vtt_path,
        layout=MagicMock(),
    )
    return service


def _make_runtime_settings(
    *,
    batch_size: int = 10,
    subdir: str = ".homeflix/thumbnails",
) -> AsyncMock:
    """Return a fake :class:`RuntimeSettings` exposing ``thumbnail_backfill``."""
    runtime = AsyncMock()
    runtime.thumbnail_backfill = AsyncMock(
        return_value=ThumbnailBackfillConfig(batch_size=batch_size, subdir=subdir),
    )
    return runtime


@pytest.mark.unit
class TestThumbnailBackfillJob:
    @pytest.mark.asyncio
    async def test_processes_movies_first_then_episodes_within_budget(
        self,
        tmp_path: Path,
    ) -> None:
        # Source files must exist on disk for the job to attempt generation.
        movie_file = tmp_path / "movie.mkv"
        movie_file.write_bytes(b"\x00")
        episode_file = tmp_path / "episode.mkv"
        episode_file.write_bytes(b"\x00")

        movie = _make_movie(str(movie_file))
        episode = _make_episode(str(episode_file))

        # batch_size=2 → 1 movie + 1 episode the way the contract specifies:
        # movies first, remaining budget to episodes.
        uow = _build_uow(movies_missing=[movie], episodes_missing=[episode])
        factory = MagicMock(return_value=uow)
        service = _make_thumbnail_service(tmp_path / "sprite.vtt")

        job = ThumbnailBackfillJob(
            media_uow_factory=factory,
            runtime_settings=_make_runtime_settings(batch_size=2),
            thumbnail_service=service,
        )
        await job.run()

        # Both items processed.
        assert service.generate.call_count == 2
        uow.movies.save.assert_awaited_once()
        uow.series.update_episode_scrub_preview_path.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_skips_episode_query_when_movies_consume_full_budget(
        self,
        tmp_path: Path,
    ) -> None:
        movie_files = []
        movies = []
        for i in range(3):
            f = tmp_path / f"m{i}.mkv"
            f.write_bytes(b"\x00")
            movie_files.append(f)
            movies.append(_make_movie(str(f)))

        uow = _build_uow(movies_missing=movies, episodes_missing=[_make_episode()])
        factory = MagicMock(return_value=uow)
        service = _make_thumbnail_service(tmp_path / "sprite.vtt")

        job = ThumbnailBackfillJob(
            media_uow_factory=factory,
            runtime_settings=_make_runtime_settings(batch_size=3),
            thumbnail_service=service,
        )
        await job.run()

        assert service.generate.call_count == 3
        assert uow.movies.save.await_count == 3
        # Budget exhausted by movies — no episode query, no episode update.
        uow.series.find_episodes_missing_scrub_preview.assert_not_called()
        uow.series.update_episode_scrub_preview_path.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_item_when_source_file_missing_on_disk(
        self,
        tmp_path: Path,
    ) -> None:
        # Movie file path does NOT exist — the job must not invoke ffmpeg.
        movie = _make_movie(str(tmp_path / "ghost.mkv"))

        uow = _build_uow(movies_missing=[movie], episodes_missing=[])
        factory = MagicMock(return_value=uow)
        service = _make_thumbnail_service(tmp_path / "sprite.vtt")

        job = ThumbnailBackfillJob(
            media_uow_factory=factory,
            runtime_settings=_make_runtime_settings(batch_size=5),
            thumbnail_service=service,
        )
        await job.run()

        service.generate.assert_not_called()
        uow.movies.save.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_skips_item_when_thumbnail_service_returns_none(
        self,
        tmp_path: Path,
    ) -> None:
        movie_file = tmp_path / "broken.mkv"
        movie_file.write_bytes(b"\x00")
        movie = _make_movie(str(movie_file))

        uow = _build_uow(movies_missing=[movie], episodes_missing=[])
        factory = MagicMock(return_value=uow)
        service = MagicMock()
        service.generate.return_value = None  # ffmpeg failed / duration too short / etc.

        job = ThumbnailBackfillJob(
            media_uow_factory=factory,
            runtime_settings=_make_runtime_settings(batch_size=5),
            thumbnail_service=service,
        )
        await job.run()

        service.generate.assert_called_once()
        # No persist when generation failed — keeps the row as "still missing"
        # so the next tick retries it.
        uow.movies.save.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_writes_into_configured_subdir_relative_to_media_file(
        self,
        tmp_path: Path,
    ) -> None:
        movie_file = tmp_path / "movie.mkv"
        movie_file.write_bytes(b"\x00")
        movie = _make_movie(str(movie_file))

        uow = _build_uow(movies_missing=[movie], episodes_missing=[])
        factory = MagicMock(return_value=uow)
        service = _make_thumbnail_service(tmp_path / "irrelevant.vtt")

        job = ThumbnailBackfillJob(
            media_uow_factory=factory,
            runtime_settings=_make_runtime_settings(batch_size=1, subdir="custom/thumbs"),
            thumbnail_service=service,
        )
        await job.run()

        # Service was invoked with output_dir =
        # <parent>/<sprite_subdir>/<file_stem>. The per-stem leaf keeps
        # episodes that share a season folder from overwriting each
        # other's sprite.
        call = service.generate.call_args
        assert call.args[0] == str(movie_file)
        assert call.args[1] == movie_file.parent / "custom" / "thumbs" / "movie"

    @pytest.mark.asyncio
    async def test_episodes_in_same_season_get_distinct_output_dirs(
        self,
        tmp_path: Path,
    ) -> None:
        """Two episodes that share a season directory must write to
        per-stem subfolders so their sprites don't overwrite each
        other — the bug that motivated the fix."""
        season_dir = tmp_path / "Show" / "Season 01"
        season_dir.mkdir(parents=True)
        ep1_file = season_dir / "Show.S01E01.mkv"
        ep2_file = season_dir / "Show.S01E02.mkv"
        ep1_file.write_bytes(b"\x00")
        ep2_file.write_bytes(b"\x00")

        ep1 = _make_episode(str(ep1_file))
        ep2 = _make_episode(str(ep2_file))

        uow = _build_uow(movies_missing=[], episodes_missing=[ep1, ep2])
        factory = MagicMock(return_value=uow)
        service = _make_thumbnail_service(tmp_path / "irrelevant.vtt")

        job = ThumbnailBackfillJob(
            media_uow_factory=factory,
            runtime_settings=_make_runtime_settings(batch_size=2),
            thumbnail_service=service,
        )
        await job.run()

        assert service.generate.call_count == 2
        called_output_dirs = [c.args[1] for c in service.generate.call_args_list]
        assert called_output_dirs[0] != called_output_dirs[1]
        assert called_output_dirs[0].name == "Show.S01E01"
        assert called_output_dirs[1].name == "Show.S01E02"

    @pytest.mark.asyncio
    async def test_process_movie_by_id_loads_then_generates(self, tmp_path: Path) -> None:
        movie_file = tmp_path / "movie.mkv"
        movie_file.write_bytes(b"\x00")
        movie = _make_movie(str(movie_file))
        assert movie.id is not None

        uow = _build_uow(movies_missing=[], episodes_missing=[], movie_by_id=movie)
        factory = MagicMock(return_value=uow)
        service = _make_thumbnail_service(tmp_path / "sprite.vtt")

        job = ThumbnailBackfillJob(
            media_uow_factory=factory,
            runtime_settings=_make_runtime_settings(),
            thumbnail_service=service,
        )
        ok = await job.process_movie_by_id(str(movie.id))

        assert ok is True
        uow.movies.find_by_id.assert_awaited_once()
        service.generate.assert_called_once()
        uow.movies.save.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_process_movie_by_id_skips_when_already_has_path(
        self,
        tmp_path: Path,
    ) -> None:
        # Race condition: another tick filled in scrub_preview_path between
        # the route reading it and the eager task running. The job must
        # re-check and bail out without invoking ffmpeg again.
        movie = _make_movie(str(tmp_path / "movie.mkv"))
        movie = movie.with_updates(scrub_preview_path=ImageUrl(str(tmp_path / "sprite.vtt")))
        assert movie.id is not None

        uow = _build_uow(movies_missing=[], episodes_missing=[], movie_by_id=movie)
        factory = MagicMock(return_value=uow)
        service = _make_thumbnail_service(tmp_path / "sprite.vtt")

        job = ThumbnailBackfillJob(
            media_uow_factory=factory,
            runtime_settings=_make_runtime_settings(),
            thumbnail_service=service,
        )
        ok = await job.process_movie_by_id(str(movie.id))

        assert ok is False
        service.generate.assert_not_called()
        uow.movies.save.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_process_movie_by_id_returns_false_when_movie_missing(
        self,
        tmp_path: Path,
    ) -> None:
        # Generate a valid-format id that simply has no row behind it.
        from src.modules.media.domain.value_objects import MovieId

        uow = _build_uow(movies_missing=[], episodes_missing=[], movie_by_id=None)
        factory = MagicMock(return_value=uow)
        service = _make_thumbnail_service(tmp_path / "sprite.vtt")

        job = ThumbnailBackfillJob(
            media_uow_factory=factory,
            runtime_settings=_make_runtime_settings(),
            thumbnail_service=service,
        )
        ok = await job.process_movie_by_id(str(MovieId.generate()))

        assert ok is False
        service.generate.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_episode_by_id_loads_then_generates(self, tmp_path: Path) -> None:
        episode_file = tmp_path / "episode.mkv"
        episode_file.write_bytes(b"\x00")
        episode = _make_episode(str(episode_file))
        assert episode.id is not None

        uow = _build_uow(movies_missing=[], episodes_missing=[], episode_by_id=episode)
        factory = MagicMock(return_value=uow)
        service = _make_thumbnail_service(tmp_path / "sprite.vtt")

        job = ThumbnailBackfillJob(
            media_uow_factory=factory,
            runtime_settings=_make_runtime_settings(),
            thumbnail_service=service,
        )
        ok = await job.process_episode_by_id(str(episode.id))

        assert ok is True
        uow.series.find_episode_by_id.assert_awaited_once()
        service.generate.assert_called_once()
        uow.series.update_episode_scrub_preview_path.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_log_no_op_when_nothing_to_process(self, tmp_path: Path) -> None:
        uow = _build_uow(movies_missing=[], episodes_missing=[])
        factory = MagicMock(return_value=uow)
        service = MagicMock()

        job = ThumbnailBackfillJob(
            media_uow_factory=factory,
            runtime_settings=_make_runtime_settings(batch_size=10),
            thumbnail_service=service,
        )
        # Should be a clean no-op — no persistence calls, no thumbnail
        # generation, and the run shouldn't raise.
        await job.run()

        service.generate.assert_not_called()
        uow.movies.save.assert_not_awaited()
        uow.series.update_episode_scrub_preview_path.assert_not_awaited()
