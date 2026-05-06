"""Tests for ``GetRelatedSeriesUseCase``."""

from unittest.mock import AsyncMock

import pytest

from src.modules.media.application.ports import MetadataProvider
from src.modules.media.application.use_cases.get_related_series import (
    GetRelatedSeriesInput,
    GetRelatedSeriesUseCase,
)
from src.modules.media.domain.entities import Series
from src.modules.media.domain.value_objects import SeriesId, TmdbId
from tests.modules.media.unit.conftest import (
    FakeProfileLibraryAccessPort,
    make_media_uow_mock,
)

_LIBRARY_ID = "lib_test12345678"
_PROFILE_ID = "prf_test12345678"


def _series(*, title: str, tmdb_id: int | None) -> Series:
    series = Series.create(library_id=_LIBRARY_ID, title=title, start_year=2010)
    return series.with_updates(tmdb_id=TmdbId(tmdb_id)) if tmdb_id is not None else series


def _make_use_case(mocks, provider, *, allowed: list[str] | None = None) -> GetRelatedSeriesUseCase:
    if allowed is None:
        allowed = [_LIBRARY_ID]
    return GetRelatedSeriesUseCase(
        mocks.factory,
        provider,
        FakeProfileLibraryAccessPort({_PROFILE_ID: allowed}),
    )


class TestGetRelatedSeriesUseCase:
    @pytest.mark.asyncio
    async def test_returns_empty_when_source_series_missing(self) -> None:
        mocks = make_media_uow_mock()
        mocks.series.find_by_id.return_value = None
        provider = AsyncMock(spec=MetadataProvider)

        use_case = _make_use_case(mocks, provider)
        result = await use_case.execute(
            GetRelatedSeriesInput(profile_id=_PROFILE_ID, series_id=str(SeriesId.generate())),
        )

        assert result == []
        provider.get_series_recommendations.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_empty_when_source_has_no_tmdb_id(self) -> None:
        # Series was added manually (no enrich) — no way to look up
        # recommendations. Bail before hitting the provider.
        mocks = make_media_uow_mock()
        mocks.series.find_by_id.return_value = _series(title="Manual", tmdb_id=None)
        provider = AsyncMock(spec=MetadataProvider)

        use_case = _make_use_case(mocks, provider)
        result = await use_case.execute(
            GetRelatedSeriesInput(profile_id=_PROFILE_ID, series_id=str(SeriesId.generate())),
        )

        assert result == []
        provider.get_series_recommendations.assert_not_called()

    @pytest.mark.asyncio
    async def test_filters_to_local_catalog_preserving_tmdb_order(self) -> None:
        # TMDB returns 4 ids in relevance order. Only ids 1396 and 60625
        # exist locally; the response must be ordered [1396, 60625] —
        # TMDB's relevance ranking, NOT the dict's insertion order.
        mocks = make_media_uow_mock()
        source = _series(title="Better Call Saul", tmdb_id=60059)
        mocks.series.find_by_id.return_value = source
        mocks.series.find_by_tmdb_ids.return_value = {
            60625: _series(title="Rick and Morty", tmdb_id=60625),
            1396: _series(title="Breaking Bad", tmdb_id=1396),
        }
        provider = AsyncMock(spec=MetadataProvider)
        provider.get_series_recommendations.return_value = [
            1396,
            999999,
            60625,
            888888,
        ]

        use_case = _make_use_case(mocks, provider)
        result = await use_case.execute(
            GetRelatedSeriesInput(
                profile_id=_PROFILE_ID,
                series_id=str(SeriesId.generate()),
                limit=10,
            ),
        )

        assert [s.title for s in result] == ["Breaking Bad", "Rick and Morty"]
        find_by_id_kwargs = mocks.series.find_by_id.await_args.kwargs
        find_by_tmdb_ids_kwargs = mocks.series.find_by_tmdb_ids.await_args.kwargs
        assert list(find_by_id_kwargs["allowed_library_ids"]) == [_LIBRARY_ID]
        assert list(find_by_tmdb_ids_kwargs["allowed_library_ids"]) == [_LIBRARY_ID]

    @pytest.mark.asyncio
    async def test_truncates_to_limit(self) -> None:
        mocks = make_media_uow_mock()
        mocks.series.find_by_id.return_value = _series(title="Source", tmdb_id=1)
        mocks.series.find_by_tmdb_ids.return_value = {
            i: _series(title=f"S{i}", tmdb_id=i) for i in (10, 11, 12, 13, 14)
        }
        provider = AsyncMock(spec=MetadataProvider)
        provider.get_series_recommendations.return_value = [10, 11, 12, 13, 14]

        use_case = _make_use_case(mocks, provider)
        result = await use_case.execute(
            GetRelatedSeriesInput(
                profile_id=_PROFILE_ID,
                series_id=str(SeriesId.generate()),
                limit=3,
            ),
        )

        assert len(result) == 3
        assert [s.title for s in result] == ["S10", "S11", "S12"]

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_local_overlap(self) -> None:
        mocks = make_media_uow_mock()
        mocks.series.find_by_id.return_value = _series(title="Source", tmdb_id=1)
        mocks.series.find_by_tmdb_ids.return_value = {}
        provider = AsyncMock(spec=MetadataProvider)
        provider.get_series_recommendations.return_value = [99, 100, 101]

        use_case = _make_use_case(mocks, provider)
        result = await use_case.execute(
            GetRelatedSeriesInput(profile_id=_PROFILE_ID, series_id=str(SeriesId.generate())),
        )

        assert result == []

    @pytest.mark.asyncio
    async def test_returns_empty_when_provider_returns_nothing(self) -> None:
        mocks = make_media_uow_mock()
        mocks.series.find_by_id.return_value = _series(title="Source", tmdb_id=1)
        provider = AsyncMock(spec=MetadataProvider)
        provider.get_series_recommendations.return_value = []

        use_case = _make_use_case(mocks, provider)
        result = await use_case.execute(
            GetRelatedSeriesInput(profile_id=_PROFILE_ID, series_id=str(SeriesId.generate())),
        )

        assert result == []
        # Should not even hit the repo on an empty TMDB result.
        mocks.series.find_by_tmdb_ids.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_empty_for_deny_all_profile(self) -> None:
        mocks = make_media_uow_mock()
        provider = AsyncMock(spec=MetadataProvider)

        use_case = _make_use_case(mocks, provider, allowed=[])
        result = await use_case.execute(
            GetRelatedSeriesInput(profile_id=_PROFILE_ID, series_id=str(SeriesId.generate())),
        )

        assert result == []
        mocks.factory.assert_not_called()
        provider.get_series_recommendations.assert_not_called()
