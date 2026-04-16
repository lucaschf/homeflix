"""Tests for ScanMediaDirectoriesUseCase."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.modules.media.application.dtos.scan_dtos import ScanMediaInput, ScanMediaOutput
from src.modules.media.application.ports import MediaType, ScannedFile
from src.modules.media.application.use_cases.scan_media_directories import (
    ScanMediaDirectoriesUseCase,
)
from src.modules.media.domain.entities import Episode, Movie, Season, Series
from src.modules.media.domain.repositories import MovieRepository, SeriesRepository
from src.modules.media.domain.value_objects import (
    Duration,
    EpisodeNumber,
    MediaFile,
    Resolution,
    SeasonNumber,
    Title,
)
from src.modules.media.infrastructure.file_system.variant_detector import VariantDetector
from src.modules.media.infrastructure.streaming.media_probe_service import MediaProbeService
from src.shared_kernel.value_objects.file_path import FilePath


def _movie_file(
    path: str,
    title: str = "Test Movie",
    year: int = 2024,
    resolution: str = "1080p",
    size: int = 1_000_000,
) -> ScannedFile:
    return ScannedFile(
        file_path=FilePath(path),
        file_size=size,
        media_type=MediaType.MOVIE,
        title=title,
        year=year,
        resolution=resolution,
    )


def _episode_file(
    path: str,
    series_name: str = "Test Show",
    season: int = 1,
    episode: int = 1,
    resolution: str = "1080p",
    size: int = 500_000,
) -> ScannedFile:
    return ScannedFile(
        file_path=FilePath(path),
        file_size=size,
        media_type=MediaType.EPISODE,
        title=series_name,
        series_name=series_name,
        season_number=season,
        episode_number=episode,
        resolution=resolution,
    )


def _make_use_case(
    *,
    scanner_results: list[ScannedFile] | None = None,
    movie_repo: AsyncMock | None = None,
    series_repo: AsyncMock | None = None,
    probe_service: MediaProbeService | MagicMock | None = None,
) -> ScanMediaDirectoriesUseCase:
    file_scanner = MagicMock()
    file_scanner.scan_directories.return_value = scanner_results or []

    variant_detector = VariantDetector()

    if movie_repo is None:
        movie_repo = AsyncMock(spec=MovieRepository)
        movie_repo.find_by_file_path.return_value = None
        movie_repo.save.side_effect = lambda m: m

    if series_repo is None:
        series_repo = AsyncMock(spec=SeriesRepository)
        series_repo.find_by_title.return_value = None
        series_repo.save.side_effect = lambda s: s

    return ScanMediaDirectoriesUseCase(
        file_scanner=file_scanner,
        variant_detector=variant_detector,
        movie_repository=movie_repo,
        series_repository=series_repo,
        probe_service=probe_service,
    )


@pytest.mark.unit
class TestScanMovies:
    """Tests for movie scanning."""

    @pytest.mark.asyncio
    async def test_should_create_movie_from_scanned_file(self) -> None:
        files = [_movie_file("/movies/Inception.2010.1080p.mkv", "Inception", 2010)]
        use_case = _make_use_case(scanner_results=files)

        result = await use_case.execute(ScanMediaInput())

        assert isinstance(result, ScanMediaOutput)
        assert result.movies_created == 1
        assert result.movies_updated == 0

    @pytest.mark.asyncio
    async def test_should_group_variants_into_single_movie(self) -> None:
        files = [
            _movie_file("/movies/Inception.2010.1080p.mkv", "Inception", 2010, "1080p"),
            _movie_file("/movies/Inception.2010.4K.mkv", "Inception", 2010, "4K"),
        ]
        use_case = _make_use_case(scanner_results=files)

        result = await use_case.execute(ScanMediaInput())

        assert result.movies_created == 1
        assert result.movies_updated == 0

    @pytest.mark.asyncio
    async def test_should_create_separate_movies_for_different_titles(self) -> None:
        files = [
            _movie_file("/movies/Inception.2010.1080p.mkv", "Inception", 2010),
            _movie_file("/movies/Interstellar.2014.1080p.mkv", "Interstellar", 2014),
        ]
        use_case = _make_use_case(scanner_results=files)

        result = await use_case.execute(ScanMediaInput())

        assert result.movies_created == 2

    @pytest.mark.asyncio
    async def test_should_update_existing_movie_with_new_variant(self) -> None:
        existing = Movie.create(
            title="Inception",
            year=2010,
            duration=8880,
            file_path="/movies/Inception.2010.1080p.mkv",
            file_size=4_000_000_000,
            resolution="1080p",
        )

        movie_repo = AsyncMock(spec=MovieRepository)
        movie_repo.find_by_file_path.side_effect = lambda fp: (
            existing if fp.value == "/movies/Inception.2010.1080p.mkv" else None
        )
        movie_repo.save.side_effect = lambda m: m

        files = [
            _movie_file("/movies/Inception.2010.1080p.mkv", "Inception", 2010, "1080p"),
            _movie_file("/movies/Inception.2010.4K.mkv", "Inception", 2010, "4K"),
        ]
        use_case = _make_use_case(scanner_results=files, movie_repo=movie_repo)

        result = await use_case.execute(ScanMediaInput())

        assert result.movies_updated == 1
        assert result.movies_created == 0

    @pytest.mark.asyncio
    async def test_should_return_empty_when_no_files(self) -> None:
        use_case = _make_use_case(scanner_results=[])

        result = await use_case.execute(ScanMediaInput())

        assert result.movies_created == 0
        assert result.episodes_created == 0


@pytest.mark.unit
class TestScanEpisodes:
    """Tests for episode scanning."""

    @pytest.mark.asyncio
    async def test_should_create_series_with_episode(self) -> None:
        files = [
            _episode_file("/series/Show/S01/Show.S01E01.mkv"),
        ]
        use_case = _make_use_case(scanner_results=files)

        result = await use_case.execute(ScanMediaInput())

        assert result.episodes_created == 1

    @pytest.mark.asyncio
    async def test_should_create_multiple_episodes_in_same_series(self) -> None:
        files = [
            _episode_file("/series/Show/S01/Show.S01E01.mkv", episode=1),
            _episode_file("/series/Show/S01/Show.S01E02.mkv", episode=2),
            _episode_file("/series/Show/S01/Show.S01E03.mkv", episode=3),
        ]
        use_case = _make_use_case(scanner_results=files)

        result = await use_case.execute(ScanMediaInput())

        assert result.episodes_created == 3

    @pytest.mark.asyncio
    async def test_should_create_multiple_seasons(self) -> None:
        files = [
            _episode_file("/series/Show/S01/Show.S01E01.mkv", season=1, episode=1),
            _episode_file("/series/Show/S02/Show.S02E01.mkv", season=2, episode=1),
        ]
        use_case = _make_use_case(scanner_results=files)

        result = await use_case.execute(ScanMediaInput())

        assert result.episodes_created == 2

    @pytest.mark.asyncio
    async def test_should_handle_mixed_movies_and_episodes(self) -> None:
        files = [
            _movie_file("/movies/Movie.2024.mkv"),
            _episode_file("/series/Show/S01/Show.S01E01.mkv"),
        ]
        use_case = _make_use_case(scanner_results=files)

        result = await use_case.execute(ScanMediaInput())

        assert result.movies_created == 1
        assert result.episodes_created == 1


@pytest.mark.unit
class TestRescanResolutionUpgrade:
    """Tests for refreshing existing entities when rescanning."""

    @pytest.mark.asyncio
    async def test_should_upgrade_movie_unknown_resolution(self) -> None:
        existing = Movie.create(
            title="Inception",
            year=2010,
            duration=8880,
            file_path="/movies/inception.mkv",
            file_size=4_000_000_000,
            resolution="Unknown",
        )
        saved: list[Movie] = []
        movie_repo = AsyncMock(spec=MovieRepository)
        movie_repo.find_by_file_path.side_effect = lambda fp: (
            existing if fp.value == "/movies/inception.mkv" else None
        )
        movie_repo.save.side_effect = lambda m: saved.append(m) or m

        files = [_movie_file("/movies/inception.mkv", "Inception", 2010, "1080p")]
        use_case = _make_use_case(scanner_results=files, movie_repo=movie_repo)

        result = await use_case.execute(ScanMediaInput())

        assert result.movies_updated == 1
        assert saved[0].files[0].resolution == Resolution("1080p")

    @pytest.mark.asyncio
    async def test_should_not_overwrite_known_movie_resolution(self) -> None:
        existing = Movie.create(
            title="Inception",
            year=2010,
            duration=8880,
            file_path="/movies/inception.mkv",
            file_size=4_000_000_000,
            resolution="1080p",
        )
        movie_repo = AsyncMock(spec=MovieRepository)
        movie_repo.find_by_file_path.side_effect = lambda fp: (
            existing if fp.value == "/movies/inception.mkv" else None
        )
        movie_repo.save.side_effect = lambda m: m

        # Same path, but scanned now reports a different/Unknown resolution
        files = [_movie_file("/movies/inception.mkv", "Inception", 2010, None)]
        use_case = _make_use_case(scanner_results=files, movie_repo=movie_repo)

        result = await use_case.execute(ScanMediaInput())

        assert result.movies_updated == 0
        movie_repo.save.assert_not_called()

    @pytest.mark.asyncio
    async def test_should_skip_when_rescan_also_returns_no_resolution(self) -> None:
        existing = Movie.create(
            title="Inception",
            year=2010,
            duration=8880,
            file_path="/movies/inception.mkv",
            file_size=4_000_000_000,
            resolution="Unknown",
        )
        movie_repo = AsyncMock(spec=MovieRepository)
        movie_repo.find_by_file_path.side_effect = lambda fp: (
            existing if fp.value == "/movies/inception.mkv" else None
        )
        movie_repo.save.side_effect = lambda m: m

        files = [_movie_file("/movies/inception.mkv", "Inception", 2010, None)]
        use_case = _make_use_case(scanner_results=files, movie_repo=movie_repo)

        result = await use_case.execute(ScanMediaInput())

        assert result.movies_updated == 0
        movie_repo.save.assert_not_called()

    @pytest.mark.asyncio
    async def test_should_probe_when_creating_movie_without_filename_resolution(
        self,
    ) -> None:
        probe = MagicMock(spec=MediaProbeService)
        probe.probe_resolution.return_value = "1080p"
        files = [_movie_file("/movies/inception.mkv", "Inception", 2010, None)]
        use_case = _make_use_case(scanner_results=files, probe_service=probe)

        result = await use_case.execute(ScanMediaInput())

        assert result.movies_created == 1
        probe.probe_resolution.assert_called_once_with("/movies/inception.mkv")

    @pytest.mark.asyncio
    async def test_should_probe_when_existing_resolution_is_unknown(self) -> None:
        existing = Movie.create(
            title="Inception",
            year=2010,
            duration=8880,
            file_path="/movies/inception.mkv",
            file_size=4_000_000_000,
            resolution="Unknown",
        )
        movie_repo = AsyncMock(spec=MovieRepository)
        movie_repo.find_by_file_path.side_effect = lambda fp: (
            existing if fp.value == "/movies/inception.mkv" else None
        )
        saved: list[Movie] = []
        movie_repo.save.side_effect = lambda m: saved.append(m) or m

        probe = MagicMock(spec=MediaProbeService)
        probe.probe_resolution.return_value = "4K"

        files = [_movie_file("/movies/inception.mkv", "Inception", 2010, None)]
        use_case = _make_use_case(
            scanner_results=files,
            movie_repo=movie_repo,
            probe_service=probe,
        )

        result = await use_case.execute(ScanMediaInput())

        assert result.movies_updated == 1
        probe.probe_resolution.assert_called_once_with("/movies/inception.mkv")
        assert saved[0].files[0].resolution == Resolution("4K")

    @pytest.mark.asyncio
    async def test_should_not_probe_when_existing_resolution_is_known(self) -> None:
        existing = Movie.create(
            title="Inception",
            year=2010,
            duration=8880,
            file_path="/movies/inception.mkv",
            file_size=4_000_000_000,
            resolution="1080p",
        )
        movie_repo = AsyncMock(spec=MovieRepository)
        movie_repo.find_by_file_path.side_effect = lambda fp: (
            existing if fp.value == "/movies/inception.mkv" else None
        )
        movie_repo.save.side_effect = lambda m: m

        probe = MagicMock(spec=MediaProbeService)

        files = [_movie_file("/movies/inception.mkv", "Inception", 2010, None)]
        use_case = _make_use_case(
            scanner_results=files,
            movie_repo=movie_repo,
            probe_service=probe,
        )

        result = await use_case.execute(ScanMediaInput())

        assert result.movies_updated == 0
        probe.probe_resolution.assert_not_called()

    @pytest.mark.asyncio
    async def test_should_not_probe_when_filename_already_has_resolution(self) -> None:
        probe = MagicMock(spec=MediaProbeService)
        files = [_movie_file("/movies/inception.1080p.mkv", "Inception", 2010, "1080p")]
        use_case = _make_use_case(scanner_results=files, probe_service=probe)

        result = await use_case.execute(ScanMediaInput())

        assert result.movies_created == 1
        probe.probe_resolution.assert_not_called()

    @pytest.mark.asyncio
    async def test_should_upgrade_episode_unknown_resolution(self) -> None:
        series = Series.create(title="Show", start_year=2024)
        assert series.id is not None
        episode = Episode(
            series_id=series.id,
            season_number=SeasonNumber(1),
            episode_number=EpisodeNumber(1),
            title=Title("Pilot"),
            duration=Duration(0),
            files=[
                MediaFile(
                    file_path=FilePath("/series/Show/S01/Show.S01E01.mkv"),
                    file_size=500_000,
                    resolution=Resolution("Unknown"),
                    is_primary=True,
                )
            ],
        )
        season = Season(
            series_id=series.id,
            season_number=SeasonNumber(1),
            episodes=[episode],
        )
        series = series.with_updates(seasons=[season])

        saved: list[Series] = []
        series_repo = AsyncMock(spec=SeriesRepository)
        series_repo.find_by_title.return_value = series
        series_repo.save.side_effect = lambda s: saved.append(s) or s

        files = [
            _episode_file(
                "/series/Show/S01/Show.S01E01.mkv",
                series_name="Show",
                season=1,
                episode=1,
                resolution="720p",
            )
        ]
        use_case = _make_use_case(scanner_results=files, series_repo=series_repo)

        result = await use_case.execute(ScanMediaInput())

        assert result.episodes_updated == 1
        saved_episode = saved[0].seasons[0].episodes[0]
        assert saved_episode.files[0].resolution == Resolution("720p")
