"""Tests for ScanMediaDirectoriesUseCase."""

from unittest.mock import MagicMock

import pytest

from src.modules.media.application.dtos.scan_dtos import ScanMediaInput, ScanMediaOutput
from src.modules.media.application.ports import (
    MediaProbePort,
    MediaType,
    ProbeResult,
    ScannedFile,
)
from src.modules.media.application.use_cases.scan_media_directories import (
    ScanMediaDirectoriesUseCase,
)
from src.modules.media.domain.entities import Episode, Movie, Season, Series
from src.modules.media.domain.value_objects import (
    Duration,
    EpisodeNumber,
    MediaFile,
    Resolution,
    SeasonNumber,
    Title,
)
from src.modules.media.infrastructure.file_system.variant_detector import VariantDetector
from src.shared_kernel.value_objects.file_path import FilePath
from src.shared_kernel.value_objects.language_code import LanguageCode
from src.shared_kernel.value_objects.tracks import AudioTrack, SubtitleTrack
from tests.modules.media.unit.conftest import MediaUoWMocks, make_media_uow_mock

_LIBRARY_ID = "lib_test12345678"


def _audio_track(lang: str, *, index: int = 0) -> AudioTrack:
    return AudioTrack(
        index=index,
        language=LanguageCode(lang),
        codec="aac",
        channels=2,
        is_default=index == 0,
    )


def _subtitle_track(lang: str, *, index: int = 0) -> SubtitleTrack:
    return SubtitleTrack(
        index=index,
        language=LanguageCode(lang),
        format="srt",
        is_external=False,
    )


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
    mocks: MediaUoWMocks | None = None,
    probe_service: MediaProbePort | MagicMock | None = None,
) -> tuple[ScanMediaDirectoriesUseCase, MediaUoWMocks]:
    """Build the scan use case wired to a mock Unit of Work factory."""
    file_scanner = MagicMock()
    file_scanner.scan_directories.return_value = scanner_results or []

    variant_detector = VariantDetector()

    if mocks is None:
        mocks = make_media_uow_mock()
        mocks.movies.find_by_file_path.return_value = None
        mocks.movies.save.side_effect = lambda m: m
        mocks.series.find_by_title.return_value = None
        mocks.series.save.side_effect = lambda s: s

    use_case = ScanMediaDirectoriesUseCase(
        file_scanner=file_scanner,
        variant_detector=variant_detector,
        uow_factory=mocks.factory,
        probe_service=probe_service,
    )
    return use_case, mocks


@pytest.mark.unit
class TestScanMovies:
    """Tests for movie scanning."""

    @pytest.mark.asyncio
    async def test_should_create_movie_from_scanned_file(self) -> None:
        files = [_movie_file("/movies/Inception.2010.1080p.mkv", "Inception", 2010)]
        use_case, _ = _make_use_case(scanner_results=files)

        result = await use_case.execute(ScanMediaInput(library_id=_LIBRARY_ID))

        assert isinstance(result, ScanMediaOutput)
        assert result.movies_created == 1
        assert result.movies_updated == 0

    @pytest.mark.asyncio
    async def test_should_group_variants_into_single_movie(self) -> None:
        files = [
            _movie_file("/movies/Inception.2010.1080p.mkv", "Inception", 2010, "1080p"),
            _movie_file("/movies/Inception.2010.4K.mkv", "Inception", 2010, "4K"),
        ]
        use_case, _ = _make_use_case(scanner_results=files)

        result = await use_case.execute(ScanMediaInput(library_id=_LIBRARY_ID))

        assert result.movies_created == 1
        assert result.movies_updated == 0

    @pytest.mark.asyncio
    async def test_should_create_separate_movies_for_different_titles(self) -> None:
        files = [
            _movie_file("/movies/Inception.2010.1080p.mkv", "Inception", 2010),
            _movie_file("/movies/Interstellar.2014.1080p.mkv", "Interstellar", 2014),
        ]
        use_case, _ = _make_use_case(scanner_results=files)

        result = await use_case.execute(ScanMediaInput(library_id=_LIBRARY_ID))

        assert result.movies_created == 2

    @pytest.mark.asyncio
    async def test_should_update_existing_movie_with_new_variant(self) -> None:
        existing = Movie.create(
            library_id=_LIBRARY_ID,
            title="Inception",
            year=2010,
            duration=8880,
            file_path="/movies/Inception.2010.1080p.mkv",
            file_size=4_000_000_000,
            resolution="1080p",
        )

        mocks = make_media_uow_mock()
        mocks.movies.find_by_file_path.side_effect = lambda fp: (
            existing if fp.value == "/movies/Inception.2010.1080p.mkv" else None
        )
        mocks.movies.save.side_effect = lambda m: m

        files = [
            _movie_file("/movies/Inception.2010.1080p.mkv", "Inception", 2010, "1080p"),
            _movie_file("/movies/Inception.2010.4K.mkv", "Inception", 2010, "4K"),
        ]
        use_case, _ = _make_use_case(scanner_results=files, mocks=mocks)

        result = await use_case.execute(ScanMediaInput(library_id=_LIBRARY_ID))

        assert result.movies_updated == 1
        assert result.movies_created == 0

    @pytest.mark.asyncio
    async def test_should_return_empty_when_no_files(self) -> None:
        use_case, _ = _make_use_case(scanner_results=[])

        result = await use_case.execute(ScanMediaInput(library_id=_LIBRARY_ID))

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
        use_case, _ = _make_use_case(scanner_results=files)

        result = await use_case.execute(ScanMediaInput(library_id=_LIBRARY_ID))

        assert result.episodes_created == 1

    @pytest.mark.asyncio
    async def test_should_create_multiple_episodes_in_same_series(self) -> None:
        files = [
            _episode_file("/series/Show/S01/Show.S01E01.mkv", episode=1),
            _episode_file("/series/Show/S01/Show.S01E02.mkv", episode=2),
            _episode_file("/series/Show/S01/Show.S01E03.mkv", episode=3),
        ]
        use_case, _ = _make_use_case(scanner_results=files)

        result = await use_case.execute(ScanMediaInput(library_id=_LIBRARY_ID))

        assert result.episodes_created == 3

    @pytest.mark.asyncio
    async def test_should_create_multiple_seasons(self) -> None:
        files = [
            _episode_file("/series/Show/S01/Show.S01E01.mkv", season=1, episode=1),
            _episode_file("/series/Show/S02/Show.S02E01.mkv", season=2, episode=1),
        ]
        use_case, _ = _make_use_case(scanner_results=files)

        result = await use_case.execute(ScanMediaInput(library_id=_LIBRARY_ID))

        assert result.episodes_created == 2

    @pytest.mark.asyncio
    async def test_should_handle_mixed_movies_and_episodes(self) -> None:
        files = [
            _movie_file("/movies/Movie.2024.mkv"),
            _episode_file("/series/Show/S01/Show.S01E01.mkv"),
        ]
        use_case, _ = _make_use_case(scanner_results=files)

        result = await use_case.execute(ScanMediaInput(library_id=_LIBRARY_ID))

        assert result.movies_created == 1
        assert result.episodes_created == 1


@pytest.mark.unit
class TestRescanResolutionUpgrade:
    """Tests for refreshing existing entities when rescanning."""

    @pytest.mark.asyncio
    async def test_should_upgrade_movie_unknown_resolution(self) -> None:
        existing = Movie.create(
            library_id=_LIBRARY_ID,
            title="Inception",
            year=2010,
            duration=8880,
            file_path="/movies/inception.mkv",
            file_size=4_000_000_000,
            resolution="Unknown",
        )
        saved: list[Movie] = []
        mocks = make_media_uow_mock()
        mocks.movies.find_by_file_path.side_effect = lambda fp: (
            existing if fp.value == "/movies/inception.mkv" else None
        )
        mocks.movies.save.side_effect = lambda m: saved.append(m) or m

        files = [_movie_file("/movies/inception.mkv", "Inception", 2010, "1080p")]
        use_case, _ = _make_use_case(scanner_results=files, mocks=mocks)

        result = await use_case.execute(ScanMediaInput(library_id=_LIBRARY_ID))

        assert result.movies_updated == 1
        assert saved[0].files[0].resolution == Resolution("1080p")

    @pytest.mark.asyncio
    async def test_should_not_overwrite_known_movie_resolution(self) -> None:
        existing = Movie.create(
            library_id=_LIBRARY_ID,
            title="Inception",
            year=2010,
            duration=8880,
            file_path="/movies/inception.mkv",
            file_size=4_000_000_000,
            resolution="1080p",
        )
        mocks = make_media_uow_mock()
        mocks.movies.find_by_file_path.side_effect = lambda fp: (
            existing if fp.value == "/movies/inception.mkv" else None
        )
        mocks.movies.save.side_effect = lambda m: m

        # Same path, but scanned now reports a different/Unknown resolution
        files = [_movie_file("/movies/inception.mkv", "Inception", 2010, None)]
        use_case, _ = _make_use_case(scanner_results=files, mocks=mocks)

        result = await use_case.execute(ScanMediaInput(library_id=_LIBRARY_ID))

        assert result.movies_updated == 0
        mocks.movies.save.assert_not_called()

    @pytest.mark.asyncio
    async def test_should_skip_when_rescan_also_returns_no_resolution(self) -> None:
        existing = Movie.create(
            library_id=_LIBRARY_ID,
            title="Inception",
            year=2010,
            duration=8880,
            file_path="/movies/inception.mkv",
            file_size=4_000_000_000,
            resolution="Unknown",
        )
        mocks = make_media_uow_mock()
        mocks.movies.find_by_file_path.side_effect = lambda fp: (
            existing if fp.value == "/movies/inception.mkv" else None
        )
        mocks.movies.save.side_effect = lambda m: m

        files = [_movie_file("/movies/inception.mkv", "Inception", 2010, None)]
        use_case, _ = _make_use_case(scanner_results=files, mocks=mocks)

        result = await use_case.execute(ScanMediaInput(library_id=_LIBRARY_ID))

        assert result.movies_updated == 0
        mocks.movies.save.assert_not_called()

    @pytest.mark.asyncio
    async def test_should_probe_when_creating_movie_without_filename_resolution(
        self,
    ) -> None:
        probe = MagicMock(spec=MediaProbePort)
        probe.probe.return_value = ProbeResult(resolution="1080p")
        files = [_movie_file("/movies/inception.mkv", "Inception", 2010, None)]
        use_case, _ = _make_use_case(scanner_results=files, probe_service=probe)

        result = await use_case.execute(ScanMediaInput(library_id=_LIBRARY_ID))

        assert result.movies_created == 1
        probe.probe.assert_called_once_with("/movies/inception.mkv")

    @pytest.mark.asyncio
    async def test_should_stamp_probed_duration_on_new_movie(self) -> None:
        mocks = make_media_uow_mock()
        mocks.movies.find_by_file_path.side_effect = lambda _fp: None
        saved: list[Movie] = []
        mocks.movies.save.side_effect = lambda m: saved.append(m) or m
        probe = MagicMock(spec=MediaProbePort)
        probe.probe.return_value = ProbeResult(resolution="1080p", duration_seconds=7245)
        files = [_movie_file("/movies/inception.mkv", "Inception", 2010, None)]
        use_case, _ = _make_use_case(scanner_results=files, mocks=mocks, probe_service=probe)

        await use_case.execute(ScanMediaInput(library_id=_LIBRARY_ID))

        # Real file duration is stamped at scan time (not left 0 for enrichment).
        assert saved[0].duration.value == 7245

    @pytest.mark.asyncio
    async def test_should_probe_when_existing_resolution_is_unknown(self) -> None:
        existing = Movie.create(
            library_id=_LIBRARY_ID,
            title="Inception",
            year=2010,
            duration=8880,
            file_path="/movies/inception.mkv",
            file_size=4_000_000_000,
            resolution="Unknown",
        )
        mocks = make_media_uow_mock()
        mocks.movies.find_by_file_path.side_effect = lambda fp: (
            existing if fp.value == "/movies/inception.mkv" else None
        )
        saved: list[Movie] = []
        mocks.movies.save.side_effect = lambda m: saved.append(m) or m

        probe = MagicMock(spec=MediaProbePort)
        probe.probe.return_value = ProbeResult(resolution="4K")

        files = [_movie_file("/movies/inception.mkv", "Inception", 2010, None)]
        use_case, _ = _make_use_case(
            scanner_results=files,
            mocks=mocks,
            probe_service=probe,
        )

        result = await use_case.execute(ScanMediaInput(library_id=_LIBRARY_ID))

        assert result.movies_updated == 1
        probe.probe.assert_called_once_with("/movies/inception.mkv")
        assert saved[0].files[0].resolution == Resolution("4K")

    @pytest.mark.asyncio
    async def test_should_not_probe_on_rescan_when_resolution_known_and_tracks_populated(
        self,
    ) -> None:
        existing = Movie.create(
            library_id=_LIBRARY_ID,
            title="Inception",
            year=2010,
            duration=8880,
            file_path="/movies/inception.mkv",
            file_size=4_000_000_000,
            resolution="1080p",
        )
        # Populate both track lists so the refresh path has nothing to backfill.
        populated_file = existing.files[0].model_copy(
            update={
                "audio_tracks": [_audio_track("en")],
                "subtitle_tracks": [_subtitle_track("en")],
            }
        )
        existing = existing.with_updates(files=[populated_file])

        mocks = make_media_uow_mock()
        mocks.movies.find_by_file_path.side_effect = lambda fp: (
            existing if fp.value == "/movies/inception.mkv" else None
        )
        mocks.movies.save.side_effect = lambda m: m

        probe = MagicMock(spec=MediaProbePort)

        files = [_movie_file("/movies/inception.mkv", "Inception", 2010, "1080p")]
        use_case, _ = _make_use_case(
            scanner_results=files,
            mocks=mocks,
            probe_service=probe,
        )

        result = await use_case.execute(ScanMediaInput(library_id=_LIBRARY_ID))

        assert result.movies_updated == 0
        probe.probe.assert_not_called()

    @pytest.mark.asyncio
    async def test_should_probe_new_file_even_when_filename_has_resolution(
        self,
    ) -> None:
        """New files are always probed so audio/subtitle tracks are captured."""
        probe = MagicMock(spec=MediaProbePort)
        probe.probe.return_value = ProbeResult(
            audio_tracks=[_audio_track("en"), _audio_track("pt")],
            resolution="1080p",
        )
        files = [_movie_file("/movies/inception.1080p.mkv", "Inception", 2010, "1080p")]
        use_case, _ = _make_use_case(scanner_results=files, probe_service=probe)

        result = await use_case.execute(ScanMediaInput(library_id=_LIBRARY_ID))

        assert result.movies_created == 1
        probe.probe.assert_called_once_with("/movies/inception.1080p.mkv")

    @pytest.mark.asyncio
    async def test_should_upgrade_episode_unknown_resolution(self) -> None:
        series = Series.create(library_id=_LIBRARY_ID, title="Show", start_year=2024)
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
        mocks = make_media_uow_mock()
        mocks.series.find_by_title.return_value = series
        mocks.series.save.side_effect = lambda s: saved.append(s) or s

        files = [
            _episode_file(
                "/series/Show/S01/Show.S01E01.mkv",
                series_name="Show",
                season=1,
                episode=1,
                resolution="720p",
            )
        ]
        use_case, _ = _make_use_case(scanner_results=files, mocks=mocks)

        result = await use_case.execute(ScanMediaInput(library_id=_LIBRARY_ID))

        assert result.episodes_updated == 1
        saved_episode = saved[0].seasons[0].episodes[0]
        assert saved_episode.files[0].resolution == Resolution("720p")


@pytest.mark.unit
class TestTrackDetection:
    """Tests for audio/subtitle track detection during scan."""

    @pytest.mark.asyncio
    async def test_should_populate_tracks_on_new_movie(self) -> None:
        probe = MagicMock(spec=MediaProbePort)
        probe.probe.return_value = ProbeResult(
            audio_tracks=[_audio_track("en"), _audio_track("pt", index=1)],
            subtitle_tracks=[_subtitle_track("en"), _subtitle_track("pt", index=1)],
            resolution="1080p",
        )
        saved: list[Movie] = []
        mocks = make_media_uow_mock()
        mocks.movies.find_by_file_path.return_value = None
        mocks.movies.save.side_effect = lambda m: saved.append(m) or m

        files = [_movie_file("/movies/Inception.mkv", "Inception", 2010, "1080p")]
        use_case, _ = _make_use_case(scanner_results=files, mocks=mocks, probe_service=probe)

        result = await use_case.execute(ScanMediaInput(library_id=_LIBRARY_ID))

        assert result.movies_created == 1
        media_file = saved[0].files[0]
        assert len(media_file.audio_tracks) == 2
        assert media_file.audio_tracks[0].language == LanguageCode("en")
        assert media_file.audio_tracks[1].language == LanguageCode("pt")
        assert len(media_file.subtitle_tracks) == 2

    @pytest.mark.asyncio
    async def test_should_populate_tracks_on_new_episode(self) -> None:
        probe = MagicMock(spec=MediaProbePort)
        probe.probe.return_value = ProbeResult(
            audio_tracks=[_audio_track("ja")],
            subtitle_tracks=[_subtitle_track("en")],
            resolution="1080p",
        )
        saved: list[Series] = []
        mocks = make_media_uow_mock()
        mocks.series.find_by_title.return_value = None
        mocks.series.save.side_effect = lambda s: saved.append(s) or s

        files = [_episode_file("/series/Anime/S01/Anime.S01E01.mkv")]
        use_case, _ = _make_use_case(scanner_results=files, mocks=mocks, probe_service=probe)

        result = await use_case.execute(ScanMediaInput(library_id=_LIBRARY_ID))

        assert result.episodes_created == 1
        ep_file = saved[0].seasons[0].episodes[0].files[0]
        assert len(ep_file.audio_tracks) == 1
        assert ep_file.audio_tracks[0].language == LanguageCode("ja")
        assert len(ep_file.subtitle_tracks) == 1
        assert ep_file.subtitle_tracks[0].language == LanguageCode("en")

    @pytest.mark.asyncio
    async def test_should_backfill_empty_tracks_on_rescan(self) -> None:
        existing = Movie.create(
            library_id=_LIBRARY_ID,
            title="Inception",
            year=2010,
            duration=8880,
            file_path="/movies/inception.mkv",
            file_size=4_000_000_000,
            resolution="1080p",
        )
        saved: list[Movie] = []
        mocks = make_media_uow_mock()
        mocks.movies.find_by_file_path.side_effect = lambda fp: (
            existing if fp.value == "/movies/inception.mkv" else None
        )
        mocks.movies.save.side_effect = lambda m: saved.append(m) or m

        probe = MagicMock(spec=MediaProbePort)
        probe.probe.return_value = ProbeResult(
            audio_tracks=[_audio_track("en")],
            subtitle_tracks=[_subtitle_track("pt")],
        )

        files = [_movie_file("/movies/inception.mkv", "Inception", 2010, "1080p")]
        use_case, _ = _make_use_case(scanner_results=files, mocks=mocks, probe_service=probe)

        result = await use_case.execute(ScanMediaInput(library_id=_LIBRARY_ID))

        assert result.movies_updated == 1
        media_file = saved[0].files[0]
        assert len(media_file.audio_tracks) == 1
        assert media_file.audio_tracks[0].language == LanguageCode("en")
        assert len(media_file.subtitle_tracks) == 1

    @pytest.mark.asyncio
    async def test_should_not_overwrite_existing_tracks_on_rescan(self) -> None:
        existing = Movie.create(
            library_id=_LIBRARY_ID,
            title="Inception",
            year=2010,
            duration=8880,
            file_path="/movies/inception.mkv",
            file_size=4_000_000_000,
            resolution="1080p",
        )
        populated_file = existing.files[0].model_copy(
            update={
                "audio_tracks": [_audio_track("fr")],
                "subtitle_tracks": [_subtitle_track("fr")],
            }
        )
        existing = existing.with_updates(files=[populated_file])

        mocks = make_media_uow_mock()
        mocks.movies.find_by_file_path.side_effect = lambda fp: (
            existing if fp.value == "/movies/inception.mkv" else None
        )
        mocks.movies.save.side_effect = lambda m: m

        probe = MagicMock(spec=MediaProbePort)

        files = [_movie_file("/movies/inception.mkv", "Inception", 2010, "1080p")]
        use_case, _ = _make_use_case(scanner_results=files, mocks=mocks, probe_service=probe)

        result = await use_case.execute(ScanMediaInput(library_id=_LIBRARY_ID))

        assert result.movies_updated == 0
        probe.probe.assert_not_called()

    @pytest.mark.asyncio
    async def test_should_include_external_subtitles_in_tracks(self) -> None:
        ext_sub = SubtitleTrack(
            index=1,
            language=LanguageCode("pt"),
            format="srt",
            is_external=True,
            file_path=FilePath("/movies/inception.pt.srt"),
        )
        probe = MagicMock(spec=MediaProbePort)
        probe.probe.return_value = ProbeResult(
            audio_tracks=[_audio_track("en")],
            subtitle_tracks=[_subtitle_track("en")],
            external_subtitles=[ext_sub],
            resolution="1080p",
        )
        saved: list[Movie] = []
        mocks = make_media_uow_mock()
        mocks.movies.find_by_file_path.return_value = None
        mocks.movies.save.side_effect = lambda m: saved.append(m) or m

        files = [_movie_file("/movies/inception.mkv", "Inception", 2010, "1080p")]
        use_case, _ = _make_use_case(scanner_results=files, mocks=mocks, probe_service=probe)

        result = await use_case.execute(ScanMediaInput(library_id=_LIBRARY_ID))

        assert result.movies_created == 1
        media_file = saved[0].files[0]
        assert len(media_file.subtitle_tracks) == 2

        embedded = [t for t in media_file.subtitle_tracks if not t.is_external]
        external = [t for t in media_file.subtitle_tracks if t.is_external]
        assert len(embedded) == 1
        assert embedded[0].language == LanguageCode("en")

        assert len(external) == 1
        assert external[0].language == LanguageCode("pt")
        assert external[0].index == 1
        assert external[0].file_path == FilePath("/movies/inception.pt.srt")


@pytest.mark.unit
class TestScanLibraryIdPropagation:
    """The scan input's ``library_id`` must reach every saved entity.

    The catalog is filtered per-profile downstream by ``library_id``,
    so a regression that drops the value during scan would un-scope
    the entire newly-created catalog.
    """

    @pytest.mark.asyncio
    async def test_movie_save_carries_input_library_id(self) -> None:
        saved: list[Movie] = []
        mocks = make_media_uow_mock()
        mocks.movies.find_by_file_path.return_value = None
        mocks.movies.save.side_effect = lambda m: saved.append(m) or m
        mocks.series.find_by_title.return_value = None

        files = [_movie_file("/movies/Inception.2010.1080p.mkv", "Inception", 2010)]
        use_case, _ = _make_use_case(scanner_results=files, mocks=mocks)

        await use_case.execute(ScanMediaInput(library_id=_LIBRARY_ID))

        assert len(saved) == 1
        assert saved[0].library_id == _LIBRARY_ID

    @pytest.mark.asyncio
    async def test_series_save_carries_input_library_id(self) -> None:
        saved: list[Series] = []
        mocks = make_media_uow_mock()
        mocks.movies.find_by_file_path.return_value = None
        mocks.series.find_by_title.return_value = None
        mocks.series.save.side_effect = lambda s: saved.append(s) or s

        files = [_episode_file("/series/Show/S01/Show.S01E01.mkv")]
        use_case, _ = _make_use_case(scanner_results=files, mocks=mocks)

        await use_case.execute(ScanMediaInput(library_id=_LIBRARY_ID))

        assert len(saved) == 1
        assert saved[0].library_id == _LIBRARY_ID

    @pytest.mark.asyncio
    async def test_distinct_library_id_propagates_to_movie(self) -> None:
        """Passing a non-default library_id reaches the saved Movie."""
        saved: list[Movie] = []
        mocks = make_media_uow_mock()
        mocks.movies.find_by_file_path.return_value = None
        mocks.movies.save.side_effect = lambda m: saved.append(m) or m
        mocks.series.find_by_title.return_value = None

        files = [_movie_file("/movies/Inception.2010.1080p.mkv", "Inception", 2010)]
        use_case, _ = _make_use_case(scanner_results=files, mocks=mocks)

        other_library = "lib_otherlibrary"
        await use_case.execute(ScanMediaInput(library_id=other_library))

        assert len(saved) == 1
        assert saved[0].library_id == other_library
