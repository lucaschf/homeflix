"""Tests for FlagSeriesEnrichmentReviewUseCase."""

import pytest

from src.building_blocks.application.errors import ResourceNotFoundException
from src.modules.media.application.dtos.admin_relink_dtos import (
    FlagSeriesEnrichmentReviewInput,
)
from src.modules.media.application.use_cases.flag_series_enrichment_review import (
    FlagSeriesEnrichmentReviewUseCase,
)
from src.modules.media.domain.entities import Series
from src.modules.media.domain.value_objects import SeriesId
from tests.modules.media.unit.conftest import make_media_uow_mock

_LIBRARY_ID = "lib_test12345678"


def _make_series() -> Series:
    return Series.create(library_id=_LIBRARY_ID, title="Breaking Bad", start_year=2008)


@pytest.mark.unit
class TestFlagSeriesEnrichmentReview:
    @pytest.mark.asyncio
    async def test_should_flag_and_persist_series(self) -> None:
        series = _make_series()
        mocks = make_media_uow_mock()
        mocks.series.find_by_id.return_value = series
        mocks.series.save.side_effect = lambda s: s

        use_case = FlagSeriesEnrichmentReviewUseCase(uow_factory=mocks.factory)
        result = await use_case.execute(
            FlagSeriesEnrichmentReviewInput(series_id=str(series.id)),
        )

        assert result.series_id == str(series.id)
        assert result.needs_enrichment_review is True

        mocks.series.save.assert_called_once()
        saved = mocks.series.save.call_args.args[0]
        assert saved.needs_enrichment_review is True

    @pytest.mark.asyncio
    async def test_should_not_persist_when_already_flagged(self) -> None:
        """Idempotent: re-flagging must not write (avoids a spurious
        ``updated_at`` bump)."""
        series = _make_series().with_enrichment_review_flagged()
        mocks = make_media_uow_mock()
        mocks.series.find_by_id.return_value = series

        use_case = FlagSeriesEnrichmentReviewUseCase(uow_factory=mocks.factory)
        result = await use_case.execute(
            FlagSeriesEnrichmentReviewInput(series_id=str(series.id)),
        )

        assert result.needs_enrichment_review is True
        mocks.series.save.assert_not_called()

    @pytest.mark.asyncio
    async def test_should_raise_when_series_not_found(self) -> None:
        mocks = make_media_uow_mock()
        mocks.series.find_by_id.return_value = None

        use_case = FlagSeriesEnrichmentReviewUseCase(uow_factory=mocks.factory)

        with pytest.raises(ResourceNotFoundException):
            await use_case.execute(
                FlagSeriesEnrichmentReviewInput(series_id=str(SeriesId.generate())),
            )
