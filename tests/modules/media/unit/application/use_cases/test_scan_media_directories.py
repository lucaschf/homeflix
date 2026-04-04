"""Tests for ScanMediaDirectoriesUseCase."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.modules.media.application.dtos.scan_dtos import ScanMediaInput, ScanMediaOutput
from src.modules.media.application.ports import MediaType, ScannedFile
from src.modules.media.application.use_cases.scan_media_directories import (
    ScanMediaDirectoriesUseCase,
)
from src.modules.media.domain.entities import Movie
from src.modules.media.domain.repositories import MovieRepository, SeriesRepository
from src.modules.media.infrastructure.file_system.variant_detector import VariantDetector
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
