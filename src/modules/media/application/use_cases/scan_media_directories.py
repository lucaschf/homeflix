"""Use case for scanning media directories and registering discovered files."""

from collections import defaultdict

from src.modules.media.application.dtos.scan_dtos import ScanMediaInput, ScanMediaOutput
from src.modules.media.application.ports import FileSystemScanner, MediaType, ScannedFile
from src.modules.media.domain.entities import Episode, Movie, Season, Series
from src.modules.media.domain.repositories import MovieRepository, SeriesRepository
from src.modules.media.domain.value_objects import (
    Duration,
    MediaFile,
    Resolution,
    Title,
)
from src.modules.media.infrastructure.file_system.variant_detector import VariantDetector


class ScanMediaDirectoriesUseCase:
    """Scan filesystem directories and register discovered media files.

    Walks the configured directories, detects movies and series episodes,
    groups file variants, and persists new or updated entities.

    Args:
        file_scanner: Port for filesystem scanning.
        variant_detector: Service for grouping file variants.
        movie_repository: Repository for movie persistence.
        series_repository: Repository for series persistence.
    """

    def __init__(
        self,
        file_scanner: FileSystemScanner,
        variant_detector: VariantDetector,
        movie_repository: MovieRepository,
        series_repository: SeriesRepository,
    ) -> None:
        self._file_scanner = file_scanner
        self._variant_detector = variant_detector
        self._movie_repository = movie_repository
        self._series_repository = series_repository

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
        """Process a single group of movie file variants."""
        existing = await self._find_existing_movie(paths, by_path)
        if existing:
            return await self._update_movie(existing, paths, by_path)
        return await self._create_movie(paths, by_path)

    async def _find_existing_movie(
        self,
        paths: list[str],
        by_path: dict[str, ScannedFile],
    ) -> Movie | None:
        """Find an existing movie matching any of the given file paths."""
        for path in paths:
            movie = await self._movie_repository.find_by_file_path(by_path[path].file_path)
            if movie:
                return movie
        return None

    async def _update_movie(
        self,
        movie: Movie,
        paths: list[str],
        by_path: dict[str, ScannedFile],
    ) -> tuple[int, int]:
        """Add new file variants to an existing movie."""
        added = False
        for path in paths:
            if all(f.file_path.value != path for f in movie.files):
                movie = movie.with_file(_build_media_file(by_path[path], is_primary=False))
                added = True
        if added:
            await self._movie_repository.save(movie)
            return 0, 1
        return 0, 0

    async def _create_movie(
        self,
        paths: list[str],
        by_path: dict[str, ScannedFile],
    ) -> tuple[int, int]:
        """Create a new movie from a group of file variants."""
        first = by_path[paths[0]]
        movie = Movie.create(
            title=first.title,
            year=first.year or _current_year(),
            duration=0,
            file_path=first.file_path.value,
            file_size=first.file_size,
            resolution=first.resolution or "Unknown",
        )
        for path in paths[1:]:
            movie = movie.with_file(_build_media_file(by_path[path], is_primary=False))
        await self._movie_repository.save(movie)
        return 1, 0

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
        """Process all episodes of a single series."""
        created = 0
        updated = 0

        series = await self._series_repository.find_by_title(Title(series_name))
        if not series:
            year = min((f.year for f in files if f.year), default=_current_year())
            series = Series.create(title=series_name, start_year=year)

        ep_groups: dict[tuple[int, int], list[ScannedFile]] = defaultdict(list)
        for f in files:
            if f.season_number is not None and f.episode_number is not None:
                ep_groups[(f.season_number, f.episode_number)].append(f)

        for (season_num, episode_num), ep_files in ep_groups.items():
            series, c, u = _process_episode_group(series, season_num, episode_num, ep_files)
            created += c
            updated += u

        await self._series_repository.save(series)
        return created, updated


def _process_episode_group(
    series: Series,
    season_num: int,
    episode_num: int,
    ep_files: list[ScannedFile],
) -> tuple[Series, int, int]:
    """Process a group of files for a single episode."""
    season = series.get_season(season_num)
    if not season:
        assert series.id is not None
        season = Season(series_id=series.id, season_number=season_num)
        series = series.with_season(season)

    episode = season.get_episode(episode_num)
    if episode:
        episode, was_updated = _add_variants_to_episode(episode, ep_files)
        created, updated = 0, int(was_updated)
    else:
        episode = _create_episode(series, season_num, episode_num, ep_files)
        created, updated = 1, 0

    season = _upsert_episode_in_season(season, episode)
    series = _upsert_season_in_series(series, season)

    return series, created, updated


def _create_episode(
    series: Series,
    season_num: int,
    episode_num: int,
    ep_files: list[ScannedFile],
) -> Episode:
    """Create a new Episode from scanned files."""
    first = ep_files[0]
    assert series.id is not None
    episode = Episode(
        series_id=series.id,
        season_number=season_num,
        episode_number=episode_num,
        title=Title(f"Episode {episode_num}"),
        duration=Duration(0),
        files=[_build_media_file(first, is_primary=True)],
    )
    for f in ep_files[1:]:
        episode = episode.with_file(_build_media_file(f, is_primary=False))
    return episode


def _add_variants_to_episode(
    episode: Episode,
    ep_files: list[ScannedFile],
) -> tuple[Episode, bool]:
    """Add new file variants to an existing episode."""
    added = False
    for f in ep_files:
        if all(ef.file_path.value != f.file_path.value for ef in episode.files):
            episode = episode.with_file(_build_media_file(f, is_primary=False))
            added = True
    return episode, added


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


def _build_media_file(scanned: ScannedFile, *, is_primary: bool) -> MediaFile:
    """Build a MediaFile value object from a ScannedFile."""
    return MediaFile(
        file_path=scanned.file_path,
        file_size=scanned.file_size,
        resolution=Resolution(scanned.resolution or "Unknown"),
        is_primary=is_primary,
    )


def _current_year() -> int:
    """Return the current year."""
    from datetime import datetime

    return datetime.now().year


__all__ = ["ScanMediaDirectoriesUseCase"]
