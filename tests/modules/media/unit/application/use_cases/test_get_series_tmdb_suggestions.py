"""Tests for GetSeriesTmdbSuggestionsUseCase."""

from unittest.mock import AsyncMock

import pytest

from src.building_blocks.application.errors import ResourceNotFoundException
from src.modules.media.application.dtos.admin_relink_dtos import (
    GetSeriesTmdbSuggestionsInput,
)
from src.modules.media.application.use_cases.get_series_tmdb_suggestions import (
    GetSeriesTmdbSuggestionsUseCase,
)
from src.modules.media.domain.entities import Series
from src.modules.media.domain.value_objects import SeriesId
from src.modules.metadata.application.ports.metadata_provider_port import (
    MetadataProvider,
    SearchCandidate,
)
from tests.modules.media.unit.conftest import make_media_uow_mock

_LIBRARY_ID = "lib_test12345678"


def _make_series(title: str = "Breaking Bad", start_year: int = 2008) -> Series:
    return Series.create(library_id=_LIBRARY_ID, title=title, start_year=start_year)


def _series_candidate(tmdb_id: int, title: str, year: int | None = None) -> SearchCandidate:
    return SearchCandidate(
        tmdb_id=tmdb_id,
        media_type="tv",
        title=title,
        year=year,
        overview=None,
        poster_url=None,
    )


@pytest.mark.unit
class TestGetSeriesTmdbSuggestions:
    @pytest.mark.asyncio
    async def test_should_return_tv_candidates(self) -> None:
        series = _make_series()
        provider = AsyncMock(spec=MetadataProvider)
        provider.find_series_candidates.return_value = [
            _series_candidate(1396, "Breaking Bad", 2008),
        ]
        mocks = make_media_uow_mock()
        mocks.series.find_by_id.return_value = series

        use_case = GetSeriesTmdbSuggestionsUseCase(
            uow_factory=mocks.factory,
            metadata_provider=provider,
        )
        output = await use_case.execute(GetSeriesTmdbSuggestionsInput(series_id=str(series.id)))

        assert output.series_id == str(series.id)
        assert [s.tmdb_id for s in output.series] == [1396]
        assert output.series[0].media_type == "tv"

    @pytest.mark.asyncio
    async def test_should_retry_without_year_when_empty(self) -> None:
        series = _make_series()
        provider = AsyncMock(spec=MetadataProvider)
        # First (year-hinted) call empty, second (no year) returns a hit.
        provider.find_series_candidates.side_effect = [
            [],
            [_series_candidate(1396, "Breaking Bad", 2008)],
        ]
        mocks = make_media_uow_mock()
        mocks.series.find_by_id.return_value = series

        use_case = GetSeriesTmdbSuggestionsUseCase(
            uow_factory=mocks.factory,
            metadata_provider=provider,
        )
        output = await use_case.execute(GetSeriesTmdbSuggestionsInput(series_id=str(series.id)))

        assert [s.tmdb_id for s in output.series] == [1396]
        assert provider.find_series_candidates.await_count == 2
        # Second call dropped the year hint.
        assert provider.find_series_candidates.await_args_list[1].args[1] is None

    @pytest.mark.asyncio
    async def test_should_raise_when_series_not_found(self) -> None:
        provider = AsyncMock(spec=MetadataProvider)
        mocks = make_media_uow_mock()
        mocks.series.find_by_id.return_value = None

        use_case = GetSeriesTmdbSuggestionsUseCase(
            uow_factory=mocks.factory,
            metadata_provider=provider,
        )
        with pytest.raises(ResourceNotFoundException):
            await use_case.execute(
                GetSeriesTmdbSuggestionsInput(series_id=str(SeriesId.generate())),
            )
