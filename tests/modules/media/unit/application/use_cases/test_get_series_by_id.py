"""Tests for GetSeriesByIdUseCase."""

from unittest.mock import AsyncMock

import pytest

from src.building_blocks.application.errors import ResourceNotFoundException
from src.modules.media.application.dtos import GetSeriesByIdInput, SeriesOutput
from src.modules.media.application.ports import ProgressLookupPort
from src.modules.media.application.use_cases import GetSeriesByIdUseCase
from src.modules.media.domain.entities import Episode, Season, Series
from src.modules.media.domain.value_objects import (
    CastMember,
    Duration,
    EpisodeId,
    FilePath,
    MediaFile,
    Resolution,
    SeasonId,
    Title,
)
from tests.modules.media.unit.conftest import (
    FakeProfileLibraryAccessPort,
    make_media_uow_mock,
)

_LIBRARY_ID = "lib_test12345678"
_PROFILE_ID = "prf_test12345678"


@pytest.fixture()
def mock_progress_lookup() -> AsyncMock:
    """Create a mock ``ProgressLookupPort`` with empty results."""
    lookup = AsyncMock(spec=ProgressLookupPort)
    lookup.find_for_media_ids.return_value = {}
    return lookup


def _make_use_case(mocks, lookup, *, allowed: list[str] | None = None):
    if allowed is None:
        allowed = [_LIBRARY_ID]
    return GetSeriesByIdUseCase(
        uow_factory=mocks.factory,
        progress_lookup=lookup,
        profile_library_access=FakeProfileLibraryAccessPort({_PROFILE_ID: allowed}),
    )


class TestGetSeriesByIdUseCase:
    """Tests for GetSeriesByIdUseCase."""

    @pytest.mark.asyncio
    async def test_should_expose_cast_in_output(self, mock_progress_lookup):
        """The series output mirrors the movie shape: each cast entry
        carries name, profile_path, role and tmdb_id so the detail UI
        can render the same actor cards across both media types."""
        mocks = make_media_uow_mock()
        series = Series.create(
            library_id=_LIBRARY_ID, title="Breaking Bad", start_year=2008
        ).with_updates(
            cast=[
                CastMember(
                    name="Bryan Cranston",
                    profile_path="https://image.tmdb.org/p/bryan.jpg",
                    role="Walter White",
                    tmdb_id=17419,
                ),
                CastMember(name="Aaron Paul", role="Jesse Pinkman"),
            ],
        )
        mocks.series.find_by_id.return_value = series
        use_case = _make_use_case(mocks, mock_progress_lookup)

        result = await use_case.execute(
            GetSeriesByIdInput(profile_id=_PROFILE_ID, series_id=str(series.id))
        )

        assert len(result.cast) == 2
        assert result.cast[0].name == "Bryan Cranston"
        assert result.cast[0].profile_path == "https://image.tmdb.org/p/bryan.jpg"
        assert result.cast[0].role == "Walter White"
        assert result.cast[0].tmdb_id == 17419
        assert result.cast[1].name == "Aaron Paul"
        assert result.cast[1].profile_path is None
        assert result.cast[1].tmdb_id is None

    @pytest.mark.asyncio
    async def test_should_return_series_when_found(self, mock_progress_lookup):
        mocks = make_media_uow_mock()
        series = Series.create(
            library_id=_LIBRARY_ID,
            title="Breaking Bad",
            start_year=2008,
        )
        mocks.series.find_by_id.return_value = series
        use_case = _make_use_case(mocks, mock_progress_lookup)

        result = await use_case.execute(
            GetSeriesByIdInput(profile_id=_PROFILE_ID, series_id=str(series.id))
        )

        assert isinstance(result, SeriesOutput)
        assert result.title == "Breaking Bad"
        assert result.start_year == 2008
        assert result.is_ongoing is True
        assert result.needs_enrichment_review is False

    @pytest.mark.asyncio
    async def test_should_expose_needs_enrichment_review_flag(self, mock_progress_lookup):
        mocks = make_media_uow_mock()
        series = Series.create(
            library_id=_LIBRARY_ID,
            title="Breaking Bad",
            start_year=2008,
        ).with_enrichment_review_flagged()
        mocks.series.find_by_id.return_value = series
        use_case = _make_use_case(mocks, mock_progress_lookup)

        result = await use_case.execute(
            GetSeriesByIdInput(profile_id=_PROFILE_ID, series_id=str(series.id))
        )

        assert result.needs_enrichment_review is True

    @pytest.mark.asyncio
    async def test_should_return_series_with_seasons(self, mock_progress_lookup):
        mocks = make_media_uow_mock()
        series = Series.create(
            library_id=_LIBRARY_ID,
            title="Breaking Bad",
            start_year=2008,
            end_year=2013,
        )
        season = Season(
            id=SeasonId.generate(),
            series_id=series.id,
            season_number=1,
        )
        series = series.with_season(season)
        mocks.series.find_by_id.return_value = series
        use_case = _make_use_case(mocks, mock_progress_lookup)

        result = await use_case.execute(
            GetSeriesByIdInput(profile_id=_PROFILE_ID, series_id=str(series.id))
        )

        assert result.season_count == 1
        assert len(result.seasons) == 1
        assert result.seasons[0].season_number == 1

    @pytest.mark.asyncio
    async def test_should_return_series_with_episodes(self, mock_progress_lookup):
        mocks = make_media_uow_mock()
        series = Series.create(
            library_id=_LIBRARY_ID,
            title="Breaking Bad",
            start_year=2008,
        )
        season = Season(
            id=SeasonId.generate(),
            series_id=series.id,
            season_number=1,
        )
        episode = Episode(
            id=EpisodeId.generate(),
            series_id=series.id,
            season_number=1,
            episode_number=1,
            title=Title("Pilot"),
            duration=Duration(3600),
            files=[
                MediaFile(
                    file_path=FilePath("/series/bb/s01e01.mkv"),
                    file_size=1_500_000_000,
                    resolution=Resolution("1080p"),
                    is_primary=True,
                )
            ],
        )
        season = season.with_episode(episode)
        series = series.with_season(season)
        mocks.series.find_by_id.return_value = series
        use_case = _make_use_case(mocks, mock_progress_lookup)

        result = await use_case.execute(
            GetSeriesByIdInput(profile_id=_PROFILE_ID, series_id=str(series.id))
        )

        assert result.total_episodes == 1
        assert len(result.seasons[0].episodes) == 1
        episode_output = result.seasons[0].episodes[0]
        assert episode_output.title == "Pilot"
        assert episode_output.episode_number == 1
        assert episode_output.duration_formatted == "01:00:00"

    @pytest.mark.asyncio
    async def test_should_return_ongoing_status(self, mock_progress_lookup):
        mocks = make_media_uow_mock()
        series = Series.create(
            library_id=_LIBRARY_ID,
            title="Ongoing Show",
            start_year=2020,
        )
        mocks.series.find_by_id.return_value = series
        use_case = _make_use_case(mocks, mock_progress_lookup)

        result = await use_case.execute(
            GetSeriesByIdInput(profile_id=_PROFILE_ID, series_id=str(series.id))
        )

        assert result.is_ongoing is True
        assert result.end_year is None

    @pytest.mark.asyncio
    async def test_should_return_completed_status(self, mock_progress_lookup):
        mocks = make_media_uow_mock()
        series = Series.create(
            library_id=_LIBRARY_ID,
            title="Completed Show",
            start_year=2010,
            end_year=2015,
        )
        mocks.series.find_by_id.return_value = series
        use_case = _make_use_case(mocks, mock_progress_lookup)

        result = await use_case.execute(
            GetSeriesByIdInput(profile_id=_PROFILE_ID, series_id=str(series.id))
        )

        assert result.is_ongoing is False
        assert result.end_year == 2015

    @pytest.mark.asyncio
    async def test_should_raise_not_found_when_series_missing(self, mock_progress_lookup):
        mocks = make_media_uow_mock()
        mocks.series.find_by_id.return_value = None
        use_case = _make_use_case(mocks, mock_progress_lookup)

        with pytest.raises(ResourceNotFoundException) as exc_info:
            await use_case.execute(
                GetSeriesByIdInput(profile_id=_PROFILE_ID, series_id="ser_nonexistent1")
            )

        assert exc_info.value.resource_type == "Series"
        assert exc_info.value.resource_id == "ser_nonexistent1"

    @pytest.mark.asyncio
    async def test_should_handle_series_with_no_seasons(self, mock_progress_lookup):
        mocks = make_media_uow_mock()
        series = Series.create(
            library_id=_LIBRARY_ID,
            title="New Show",
            start_year=2024,
        )
        mocks.series.find_by_id.return_value = series
        use_case = _make_use_case(mocks, mock_progress_lookup)

        result = await use_case.execute(
            GetSeriesByIdInput(profile_id=_PROFILE_ID, series_id=str(series.id))
        )

        assert result.season_count == 0
        assert result.total_episodes == 0
        assert result.seasons == []

    @pytest.mark.asyncio
    async def test_should_return_genres_as_strings(self, mock_progress_lookup):
        mocks = make_media_uow_mock()
        series = Series.create(
            library_id=_LIBRARY_ID,
            title="Drama Show",
            start_year=2020,
            genres=["Drama", "Thriller"],
        )
        mocks.series.find_by_id.return_value = series
        use_case = _make_use_case(mocks, mock_progress_lookup)

        result = await use_case.execute(
            GetSeriesByIdInput(profile_id=_PROFILE_ID, series_id=str(series.id))
        )

        assert result.genres == ["Drama", "Thriller"]

    @pytest.mark.asyncio
    async def test_should_pass_allowed_libraries_to_repo(self, mock_progress_lookup):
        mocks = make_media_uow_mock()
        series = Series.create(library_id=_LIBRARY_ID, title="Show", start_year=2020)
        mocks.series.find_by_id.return_value = series
        use_case = _make_use_case(mocks, mock_progress_lookup)

        await use_case.execute(GetSeriesByIdInput(profile_id=_PROFILE_ID, series_id=str(series.id)))

        call_args = mocks.series.find_by_id.await_args
        assert list(call_args.kwargs["allowed_library_ids"]) == [_LIBRARY_ID]

    @pytest.mark.asyncio
    async def test_should_raise_404_for_deny_all_profile(self, mock_progress_lookup):
        # Deny-all profile must surface as 404 — same security
        # justification as for movies.
        mocks = make_media_uow_mock()
        use_case = _make_use_case(mocks, mock_progress_lookup, allowed=[])

        with pytest.raises(ResourceNotFoundException):
            await use_case.execute(
                GetSeriesByIdInput(profile_id=_PROFILE_ID, series_id="ser_anything123456")
            )
        mocks.factory.assert_not_called()
        mocks.series.find_by_id.assert_not_awaited()
