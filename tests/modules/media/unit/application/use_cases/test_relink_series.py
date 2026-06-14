"""Tests for RelinkSeriesUseCase."""

from unittest.mock import AsyncMock

import pytest

from src.building_blocks.application.errors import (
    ResourceNotFoundException,
    UseCaseValidationException,
)
from src.modules.media.application.dtos.admin_relink_dtos import RelinkSeriesInput
from src.modules.media.application.dtos.enrichment_dtos import EnrichMediaOutput
from src.modules.media.application.use_cases.enrich_series_metadata import (
    EnrichSeriesMetadataUseCase,
)
from src.modules.media.application.use_cases.relink_series import RelinkSeriesUseCase
from src.modules.media.domain.entities import Series
from src.modules.media.domain.value_objects import SeriesId
from tests.modules.media.unit.conftest import make_media_uow_mock

_LIBRARY_ID = "lib_test12345678"


def _make_series() -> Series:
    return Series.create(library_id=_LIBRARY_ID, title="Breaking Bad", start_year=2008)


@pytest.mark.unit
class TestRelinkSeries:
    @pytest.mark.asyncio
    async def test_should_stamp_tmdb_id_and_force_enrich_on_tv_pick(self) -> None:
        series = _make_series()
        mocks = make_media_uow_mock()
        mocks.series.find_by_id.return_value = series
        mocks.series.save.side_effect = lambda s: s

        enrich = AsyncMock(spec=EnrichSeriesMetadataUseCase)
        enrich.execute.return_value = EnrichMediaOutput(
            media_id=str(series.id),
            enriched=True,
            provider="tmdb",
        )

        use_case = RelinkSeriesUseCase(uow_factory=mocks.factory, enrich_use_case=enrich)
        result = await use_case.execute(
            RelinkSeriesInput(series_id=str(series.id), tmdb_id=1396, media_type="tv"),
        )

        assert result.enriched is True
        assert result.provider == "tmdb"

        mocks.series.save.assert_called_once()
        saved = mocks.series.save.call_args.args[0]
        assert saved.tmdb_id is not None
        assert saved.tmdb_id.value == 1396

        enrich.execute.assert_awaited_once()
        enrich_input = enrich.execute.await_args.args[0]
        assert enrich_input.media_id == str(series.id)
        assert enrich_input.force is True

    @pytest.mark.asyncio
    async def test_should_reject_movie_media_type_with_validation_error(self) -> None:
        mocks = make_media_uow_mock()
        enrich = AsyncMock(spec=EnrichSeriesMetadataUseCase)

        use_case = RelinkSeriesUseCase(uow_factory=mocks.factory, enrich_use_case=enrich)

        with pytest.raises(UseCaseValidationException) as excinfo:
            await use_case.execute(
                RelinkSeriesInput(
                    series_id=str(SeriesId.generate()),
                    tmdb_id=603,
                    media_type="movie",
                ),
            )

        assert excinfo.value.message_code == "RELINK_CROSS_TYPE_NOT_SUPPORTED"
        mocks.series.find_by_id.assert_not_called()
        enrich.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_should_raise_when_series_not_found(self) -> None:
        mocks = make_media_uow_mock()
        mocks.series.find_by_id.return_value = None
        enrich = AsyncMock(spec=EnrichSeriesMetadataUseCase)

        use_case = RelinkSeriesUseCase(uow_factory=mocks.factory, enrich_use_case=enrich)

        with pytest.raises(ResourceNotFoundException):
            await use_case.execute(
                RelinkSeriesInput(
                    series_id=str(SeriesId.generate()),
                    tmdb_id=1396,
                    media_type="tv",
                ),
            )
