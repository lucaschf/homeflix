"""Tests for ListSeriesNeedingReviewUseCase."""

import pytest

from src.modules.media.application.use_cases.list_series_needing_review import (
    ListSeriesNeedingReviewUseCase,
)
from src.modules.media.domain.entities import Series
from src.modules.media.domain.value_objects import TmdbId
from tests.modules.media.unit.conftest import make_media_uow_mock

_LIBRARY_ID = "lib_test12345678"


def _make_series(title: str, start_year: int, tmdb_id: int | None = None) -> Series:
    series = Series.create(library_id=_LIBRARY_ID, title=title, start_year=start_year)
    if tmdb_id is not None:
        series = series.with_updates(tmdb_id=TmdbId(tmdb_id))
    return series


@pytest.mark.unit
class TestListSeriesNeedingReview:
    @pytest.mark.asyncio
    async def test_should_return_flagged_series(self) -> None:
        flagged = [
            _make_series("Breaking Bad", 2008, tmdb_id=1396),
            _make_series("The Wire", 2002),
        ]
        mocks = make_media_uow_mock()
        mocks.series.find_needs_enrichment_review.return_value = flagged

        use_case = ListSeriesNeedingReviewUseCase(uow_factory=mocks.factory)
        output = await use_case.execute()

        assert len(output.series) == 2
        assert {s.title for s in output.series} == {"Breaking Bad", "The Wire"}
        assert all(s.id.startswith("ser_") for s in output.series)

    @pytest.mark.asyncio
    async def test_should_surface_current_tmdb_id(self) -> None:
        """The current (possibly wrong) tmdb_id helps the operator
        confirm the mismatch before relinking."""
        mocks = make_media_uow_mock()
        mocks.series.find_needs_enrichment_review.return_value = [
            _make_series("Breaking Bad", 2008, tmdb_id=1396),
        ]

        use_case = ListSeriesNeedingReviewUseCase(uow_factory=mocks.factory)
        output = await use_case.execute()

        assert output.series[0].tmdb_id == 1396

    @pytest.mark.asyncio
    async def test_should_return_empty_list_when_none_flagged(self) -> None:
        mocks = make_media_uow_mock()
        mocks.series.find_needs_enrichment_review.return_value = []

        use_case = ListSeriesNeedingReviewUseCase(uow_factory=mocks.factory)
        output = await use_case.execute()

        assert output.series == []
