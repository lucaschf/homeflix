"""Tests for GetSeriesByIdUseCase."""

from unittest.mock import AsyncMock

import pytest

from src.building_blocks.application.errors import ResourceNotFoundException
from src.modules.media.application.dtos import GetSeriesByIdInput, SeriesOutput
from src.modules.media.application.errors import (
    ContentRestrictedByMaturityError,
    ContentRestrictedUnratedError,
)
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
from src.shared_kernel.content_policy import ViewingPolicy
from src.shared_kernel.value_objects import (
    AgeRating,
    Certification,
    ContentRating,
    LibraryId,
    RatingSystem,
)
from tests.modules.media.unit.conftest import (
    FakeProfileViewingPolicyPort,
    FixedViewingPolicyPort,
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
        profile_viewing_policy=FakeProfileViewingPolicyPort({_PROFILE_ID: allowed}),
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
        assert call_args.kwargs["policy"] == ViewingPolicy.unrestricted([_LIBRARY_ID])

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


_OTHER_LIBRARY_ID = "lib_other1234567"
_TITLE = "Restricted Show"


def _certification(label: str, age: int | None) -> Certification:
    return Certification(
        system=RatingSystem.BR_DEJUS if age is not None else RatingSystem.UNKNOWN,
        label=ContentRating(label),
        minimum_age=AgeRating(age) if age is not None else None,
    )


def _rated_series(certification: Certification | None, *, library_id: str = _LIBRARY_ID) -> Series:
    return Series.create(
        library_id=library_id,
        title=_TITLE,
        start_year=2020,
        certification=certification,
    )


def _serve_as_repository(mocks, series: Series) -> None:
    """Make ``find_by_id`` answer the way the SQL projection of ``policy`` would.

    Emulating the repository's full-policy filter, instead of returning
    the series unconditionally, is what makes these tests notice a use
    case that passes the full policy: the over-age series would come
    back ``None`` and surface as a 404.
    """

    async def _find_by_id(series_id, *, policy=None):
        if str(series_id) != str(series.id):
            return None
        if policy is not None and not policy.permits(
            library_id=LibraryId(series.library_id), minimum_age=series.minimum_age
        ):
            return None
        return series

    mocks.series.find_by_id.side_effect = _find_by_id


def _make_limited_use_case(
    mocks, lookup, limit: int, *, libraries: list[str] | None = None
) -> GetSeriesByIdUseCase:
    return GetSeriesByIdUseCase(
        uow_factory=mocks.factory,
        progress_lookup=lookup,
        profile_viewing_policy=FixedViewingPolicyPort(
            ViewingPolicy(
                allowed_library_ids=[_LIBRARY_ID] if libraries is None else libraries,
                maturity_limit=AgeRating(limit),
            )
        ),
    )


class TestGetSeriesByIdMaturityGate:
    """ADR-035 §11: 404 on the library axis, 403 on the maturity axis."""

    async def test_should_raise_maturity_403_without_the_title_when_above_limit(
        self, mock_progress_lookup
    ):
        mocks = make_media_uow_mock()
        series = _rated_series(_certification("16", 16))
        _serve_as_repository(mocks, series)
        use_case = _make_limited_use_case(mocks, mock_progress_lookup, 12)

        with pytest.raises(ContentRestrictedByMaturityError) as exc_info:
            await use_case.execute(
                GetSeriesByIdInput(profile_id=_PROFILE_ID, series_id=str(series.id))
            )

        exc = exc_info.value
        assert exc.code == "CONTENT_RESTRICTED_BY_MATURITY"
        body = exc.to_dict()
        assert body["details"] == [
            {
                "code": "CONTENT_RESTRICTED_BY_MATURITY",
                "message": "Requires age 16; profile limit is 12",
                "metadata": {"required_age": 16, "profile_limit": 12},
            }
        ]
        assert _TITLE not in str(body)
        assert str(series.id) not in str(body)
        # Refused before any per-episode progress is read.
        mock_progress_lookup.find_for_media_ids.assert_not_awaited()

    @pytest.mark.parametrize(
        "certification",
        [None, _certification("NR", None)],
        ids=["no-certification", "undetermined-label"],
    )
    async def test_should_raise_unrated_403_when_unrated_under_a_limit_below_adult(
        self, mock_progress_lookup, certification
    ):
        mocks = make_media_uow_mock()
        series = _rated_series(certification)
        _serve_as_repository(mocks, series)
        use_case = _make_limited_use_case(mocks, mock_progress_lookup, 12)

        with pytest.raises(ContentRestrictedUnratedError) as exc_info:
            await use_case.execute(
                GetSeriesByIdInput(profile_id=_PROFILE_ID, series_id=str(series.id))
            )

        body = exc_info.value.to_dict()
        assert body["code"] == "CONTENT_RESTRICTED_UNRATED"
        assert body["details"][0]["metadata"] == {"profile_limit": 12}
        assert _TITLE not in str(body)

    async def test_should_return_unrated_series_under_an_adult_limit(self, mock_progress_lookup):
        mocks = make_media_uow_mock()
        series = _rated_series(None)
        _serve_as_repository(mocks, series)
        use_case = _make_limited_use_case(mocks, mock_progress_lookup, 18)

        result = await use_case.execute(
            GetSeriesByIdInput(profile_id=_PROFILE_ID, series_id=str(series.id))
        )

        assert result.title == _TITLE

    async def test_should_return_series_within_the_limit(self, mock_progress_lookup):
        mocks = make_media_uow_mock()
        series = _rated_series(_certification("12", 12))
        _serve_as_repository(mocks, series)
        use_case = _make_limited_use_case(mocks, mock_progress_lookup, 12)

        result = await use_case.execute(
            GetSeriesByIdInput(profile_id=_PROFILE_ID, series_id=str(series.id))
        )

        assert result.title == _TITLE
        assert result.content_rating == "12"

    async def test_should_raise_404_not_403_when_outside_libraries_and_above_limit(
        self, mock_progress_lookup
    ):
        # The library axis takes precedence and hides existence.
        mocks = make_media_uow_mock()
        series = _rated_series(_certification("18", 18), library_id=_OTHER_LIBRARY_ID)
        _serve_as_repository(mocks, series)
        use_case = _make_limited_use_case(mocks, mock_progress_lookup, 12)

        with pytest.raises(ResourceNotFoundException) as exc_info:
            await use_case.execute(
                GetSeriesByIdInput(profile_id=_PROFILE_ID, series_id=str(series.id))
            )

        assert type(exc_info.value) is ResourceNotFoundException

    async def test_should_raise_404_for_deny_all_profile_with_a_limit(self, mock_progress_lookup):
        mocks = make_media_uow_mock()
        use_case = _make_limited_use_case(mocks, mock_progress_lookup, 12, libraries=[])

        with pytest.raises(ResourceNotFoundException) as exc_info:
            await use_case.execute(
                GetSeriesByIdInput(profile_id=_PROFILE_ID, series_id="ser_anything123456")
            )

        assert type(exc_info.value) is ResourceNotFoundException
        mocks.factory.assert_not_called()
