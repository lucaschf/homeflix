"""Use case for scanning media directories and registering discovered files."""

import asyncio
from collections import defaultdict

from src.building_blocks.application.event_bus import EventBus
from src.building_blocks.domain.events import DomainEvent
from src.modules.media.application.dtos.scan_dtos import ScanMediaInput, ScanMediaOutput
from src.modules.media.application.ports import (
    FileSystemScanner,
    MediaProbePort,
    MediaType,
    ProbeResult,
    ScannedFile,
    VariantDetectorPort,
)
from src.modules.media.application.unit_of_work import (
    MediaUnitOfWork,
    MediaUnitOfWorkFactory,
)
from src.modules.media.domain.entities import Episode, Movie, Season, Series
from src.modules.media.domain.events import MediaCreatedEvent
from src.modules.media.domain.value_objects import (
    Duration,
    EpisodeNumber,
    MediaFile,
    MovieId,
    Resolution,
    SeasonNumber,
    Title,
    Year,
)


class ScanMediaDirectoriesUseCase:
    """Scan filesystem directories and register discovered media files.

    Walks the configured directories, detects movies and series episodes,
    groups file variants, and persists new or updated entities. New files
    are always probed via ``probe_service`` to detect audio and subtitle
    tracks (including their languages). Existing files are re-probed only
    when their stored resolution is ``Unknown`` or their track lists are
    still empty, so rescans of fully-populated libraries skip ffprobe.

    Each movie group and each series is persisted in its own Unit of
    Work so a failure on one group rolls back only that transaction —
    other groups discovered in the same scan commit independently.

    Args:
        file_scanner: Port for filesystem scanning.
        variant_detector: Port for grouping file variants.
        uow_factory: Factory that opens a fresh media Unit of Work per group.
        probe_service: Optional probe port for track and resolution detection.
        event_bus: Optional event bus for domain events.
    """

    def __init__(
        self,
        file_scanner: FileSystemScanner,
        variant_detector: VariantDetectorPort,
        uow_factory: MediaUnitOfWorkFactory,
        probe_service: MediaProbePort | None = None,
        event_bus: EventBus | None = None,
    ) -> None:
        self._file_scanner = file_scanner
        self._variant_detector = variant_detector
        self._uow_factory = uow_factory
        self._probe_service = probe_service
        self._event_bus = event_bus

    async def execute(self, input_dto: ScanMediaInput) -> ScanMediaOutput:
        """Execute the media scan.

        Args:
            input_dto: Scan input with directories to scan.

        Returns:
            Summary of created and updated entities.
        """
        scanned_files = self._file_scanner.scan_directories(input_dto.directories)

        movies = [f for f in scanned_files if f.media_type == MediaType.MOVIE]
        episodes = [f for f in scanned_files if f.media_type == MediaType.EPISODE]

        movies_created, movies_updated, movie_errors = await self._process_movies(movies)
        episodes_created, episodes_updated, episode_errors = await self._process_episodes(
            episodes,
        )

        return ScanMediaOutput(
            movies_created=movies_created,
            movies_updated=movies_updated,
            episodes_created=episodes_created,
            episodes_updated=episodes_updated,
            errors=[*movie_errors, *episode_errors],
        )

    async def _dispatch_events(self, events: list[DomainEvent]) -> None:
        """Dispatch domain events via the event bus, if available."""
        if not self._event_bus:
            return
        for event in events:
            await self._event_bus.publish(event)

    # =========================================================================
    # ffprobe integration
    # =========================================================================

    async def _probe(self, file_path: str) -> ProbeResult | None:
        """Run full ffprobe in a worker thread.

        Returns the complete probe result (tracks + resolution) or ``None``
        when probing is unavailable.
        """
        if self._probe_service is None:
            return None
        return await asyncio.to_thread(self._probe_service.probe, file_path)

    async def _build_new_media_file(
        self,
        scanned: ScannedFile,
        *,
        is_primary: bool,
    ) -> MediaFile:
        """Build a MediaFile for a path being registered for the first time.

        Always probes the file so audio and subtitle tracks — including their
        languages — are persisted on first registration.
        """
        probed = await self._probe(scanned.file_path.value)
        resolution = scanned.resolution or (probed.resolution if probed else None) or "Unknown"
        return MediaFile(
            file_path=scanned.file_path,
            file_size=scanned.file_size,
            resolution=Resolution(resolution),
            audio_tracks=list(probed.audio_tracks) if probed else [],
            subtitle_tracks=list(probed.all_subtitles) if probed else [],
            is_primary=is_primary,
        )

    async def _maybe_refresh_media_file(
        self,
        current: MediaFile,
        scanned: ScannedFile,
    ) -> MediaFile | None:
        """Return a refreshed MediaFile when stored metadata can be enriched.

        Upgrades ``Unknown`` resolutions and backfills empty audio or
        subtitle track lists independently. Never overwrites a known
        resolution or non-empty track lists. Returns ``None`` when no
        change is needed.
        """
        needs_resolution = current.resolution.name == "Unknown"
        needs_audio = not current.audio_tracks
        needs_subtitles = not current.subtitle_tracks
        if not needs_resolution and not needs_audio and not needs_subtitles:
            return None

        updates: dict[str, object] = {}

        if needs_resolution and scanned.resolution:
            updates["resolution"] = Resolution(scanned.resolution)
            needs_resolution = False

        if needs_resolution or needs_audio or needs_subtitles:
            probed = await self._probe(scanned.file_path.value)
            if probed is not None:
                if needs_resolution and probed.resolution:
                    updates["resolution"] = Resolution(probed.resolution)
                if needs_audio and probed.audio_tracks:
                    updates["audio_tracks"] = list(probed.audio_tracks)
                if needs_subtitles and probed.all_subtitles:
                    updates["subtitle_tracks"] = list(probed.all_subtitles)

        if not updates:
            return None
        return current.model_copy(update=updates)

    # =========================================================================
    # Movies
    # =========================================================================

    async def _process_movies(
        self,
        files: list[ScannedFile],
    ) -> tuple[int, int, list[str]]:
        """Process scanned movie files."""
        created = 0
        updated = 0
        errors: list[str] = []

        file_paths = [f.file_path.value for f in files]
        groups = self._variant_detector.group_variants(file_paths)
        by_path = {f.file_path.value: f for f in files}

        for _base_name, paths in groups.items():
            try:
                c, u = await self._process_movie_group(paths, by_path)
                created += c
                updated += u
            except Exception as e:
                errors.append(f"Error processing movie files {paths}: {e}")

        return created, updated, errors

    async def _process_movie_group(
        self,
        paths: list[str],
        by_path: dict[str, ScannedFile],
    ) -> tuple[int, int]:
        """Process a single group of movie file variants in its own UoW."""
        async with self._uow_factory() as uow:
            existing = await self._find_existing_movie(uow, paths, by_path)
            if existing:
                created, updated, events = await self._update_movie(uow, existing, paths, by_path)
            else:
                created, updated, events = await self._create_movie(uow, paths, by_path)
        await self._dispatch_events(events)
        return created, updated

    @staticmethod
    async def _find_existing_movie(
        uow: MediaUnitOfWork,
        paths: list[str],
        by_path: dict[str, ScannedFile],
    ) -> Movie | None:
        """Find an existing movie matching any of the given file paths."""
        for path in paths:
            movie = await uow.movies.find_by_file_path(by_path[path].file_path)
            if movie:
                return movie
        return None

    async def _update_movie(
        self,
        uow: MediaUnitOfWork,
        movie: Movie,
        paths: list[str],
        by_path: dict[str, ScannedFile],
    ) -> tuple[int, int, list[DomainEvent]]:
        """Add new file variants and refresh existing ones from a fresh scan."""
        files = list(movie.files)
        changed = False

        for path in paths:
            scanned = by_path[path]
            existing_idx = next(
                (i for i, f in enumerate(files) if f.file_path.value == path),
                None,
            )
            if existing_idx is None:
                files.append(await self._build_new_media_file(scanned, is_primary=False))
                changed = True
                continue

            refreshed = await self._maybe_refresh_media_file(files[existing_idx], scanned)
            if refreshed is not None:
                files[existing_idx] = refreshed
                changed = True

        if changed:
            movie = movie.with_updates(files=files)
            events = movie.pull_events()
            await uow.movies.save(movie)
            return 0, 1, events
        return 0, 0, []

    async def _create_movie(
        self,
        uow: MediaUnitOfWork,
        paths: list[str],
        by_path: dict[str, ScannedFile],
    ) -> tuple[int, int, list[DomainEvent]]:
        """Create a new movie from a group of file variants."""
        first = by_path[paths[0]]
        primary_file = await self._build_new_media_file(first, is_primary=True)
        movie_id = MovieId.generate()
        movie = Movie(
            id=movie_id,
            title=Title(first.title),
            year=Year(first.year or _current_year()),
            duration=Duration(0),
            files=[primary_file],
        )
        movie.add_event(MediaCreatedEvent(media_id=str(movie_id), media_type="movie"))
        for path in paths[1:]:
            movie = movie.with_file(
                await self._build_new_media_file(by_path[path], is_primary=False)
            )
        events = movie.pull_events()
        await uow.movies.save(movie)
        return 1, 0, events

    # =========================================================================
    # Episodes
    # =========================================================================

    async def _process_episodes(
        self,
        files: list[ScannedFile],
    ) -> tuple[int, int, list[str]]:
        """Process scanned episode files."""
        created = 0
        updated = 0
        errors: list[str] = []

        by_series: dict[str, list[ScannedFile]] = defaultdict(list)
        for f in files:
            if f.series_name:
                by_series[f.series_name].append(f)

        for series_name, series_files in by_series.items():
            try:
                c, u = await self._process_series(series_name, series_files)
                created += c
                updated += u
            except Exception as e:
                errors.append(f"Error processing series '{series_name}': {e}")

        return created, updated, errors

    async def _process_series(
        self,
        series_name: str,
        files: list[ScannedFile],
    ) -> tuple[int, int]:
        """Process all episodes of a single series in its own UoW."""
        created = 0
        updated = 0

        async with self._uow_factory() as uow:
            series = await uow.series.find_by_title(Title(series_name))
            if not series:
                year = min((f.year for f in files if f.year), default=_current_year())
                series = Series.create(title=series_name, start_year=year)

            ep_groups: dict[tuple[int, int], list[ScannedFile]] = defaultdict(list)
            for f in files:
                if f.season_number is not None and f.episode_number is not None:
                    ep_groups[(f.season_number, f.episode_number)].append(f)

            for (season_num, episode_num), ep_files in ep_groups.items():
                series, c, u = await self._process_episode_group(
                    series, season_num, episode_num, ep_files
                )
                created += c
                updated += u

            events = series.pull_events()
            await uow.series.save(series)
        await self._dispatch_events(events)
        return created, updated

    async def _process_episode_group(
        self,
        series: Series,
        season_num: int,
        episode_num: int,
        ep_files: list[ScannedFile],
    ) -> tuple[Series, int, int]:
        """Process a group of files for a single episode."""
        season = series.get_season(season_num)
        if not season:
            if series.id is None:
                raise RuntimeError("Series id must be assigned before creating seasons")
            season = Season(series_id=series.id, season_number=SeasonNumber(season_num))
            series = series.with_season(season)

        episode = season.get_episode(episode_num)
        if episode:
            episode, was_updated = await self._refresh_episode(episode, ep_files)
            created, updated = 0, int(was_updated)
        else:
            episode = await self._create_episode(series, season_num, episode_num, ep_files)
            created, updated = 1, 0

        season = _upsert_episode_in_season(season, episode)
        series = _upsert_season_in_series(series, season)

        return series, created, updated

    async def _create_episode(
        self,
        series: Series,
        season_num: int,
        episode_num: int,
        ep_files: list[ScannedFile],
    ) -> Episode:
        """Create a new Episode from scanned files."""
        first = ep_files[0]
        if series.id is None:
            raise RuntimeError("Series id must be assigned before creating episodes")
        ep_title = first.episode_title or f"Episode {episode_num}"
        episode = Episode(
            series_id=series.id,
            season_number=SeasonNumber(season_num),
            episode_number=EpisodeNumber(episode_num),
            title=Title(ep_title),
            duration=Duration(0),
            files=[await self._build_new_media_file(first, is_primary=True)],
        )
        for f in ep_files[1:]:
            episode = episode.with_file(await self._build_new_media_file(f, is_primary=False))
        return episode

    async def _refresh_episode(
        self,
        episode: Episode,
        ep_files: list[ScannedFile],
    ) -> tuple[Episode, bool]:
        """Add new file variants and refresh existing ones from a fresh scan."""
        files = list(episode.files)
        changed = False

        for scanned in ep_files:
            existing_idx = next(
                (i for i, f in enumerate(files) if f.file_path.value == scanned.file_path.value),
                None,
            )
            if existing_idx is None:
                files.append(await self._build_new_media_file(scanned, is_primary=False))
                changed = True
                continue

            refreshed = await self._maybe_refresh_media_file(files[existing_idx], scanned)
            if refreshed is not None:
                files[existing_idx] = refreshed
                changed = True

        if changed:
            episode = episode.with_updates(files=files)
        return episode, changed


def _upsert_episode_in_season(season: Season, episode: Episode) -> Season:
    """Replace or append an episode in a season's episode list."""
    episodes = list(season.episodes)
    for idx, existing in enumerate(episodes):
        if existing.episode_number == episode.episode_number:
            episodes[idx] = episode
            break
    else:
        episodes.append(episode)
    return season.with_updates(episodes=episodes)


def _upsert_season_in_series(series: Series, season: Season) -> Series:
    """Replace or append a season in a series' season list."""
    seasons = list(series.seasons)
    for idx, existing in enumerate(seasons):
        if existing.season_number == season.season_number:
            seasons[idx] = season
            break
    else:
        seasons.append(season)
    return series.with_updates(seasons=seasons)


def _current_year() -> int:
    """Return the current year."""
    from datetime import datetime

    return datetime.now().year


__all__ = ["ScanMediaDirectoriesUseCase"]
