"""Tests for DeleteSeriesUseCase."""

import pytest

from src.building_blocks.application.errors import ResourceNotFoundException
from src.modules.media.application.dtos.series_dtos import DeleteSeriesInput
from src.modules.media.application.use_cases.delete_series import DeleteSeriesUseCase
from tests.modules.media.unit.conftest import make_media_uow_mock


class TestDeleteSeriesUseCase:
    """Tests for DeleteSeriesUseCase — mirrors DeleteMovieUseCase."""

    @pytest.mark.asyncio
    async def test_should_delete_series_when_found(self) -> None:
        mocks = make_media_uow_mock()
        mocks.series.delete.return_value = True
        use_case = DeleteSeriesUseCase(uow_factory=mocks.factory)

        await use_case.execute(DeleteSeriesInput(series_id="ser_abc123def456"))

        mocks.series.delete.assert_called_once()
        mocks.factory.assert_called_once()

    @pytest.mark.asyncio
    async def test_should_raise_not_found_when_series_missing(self) -> None:
        mocks = make_media_uow_mock()
        mocks.series.delete.return_value = False
        use_case = DeleteSeriesUseCase(uow_factory=mocks.factory)

        with pytest.raises(ResourceNotFoundException) as exc_info:
            await use_case.execute(DeleteSeriesInput(series_id="ser_nonexistent1"))

        assert exc_info.value.resource_type == "Series"
        assert exc_info.value.resource_id == "ser_nonexistent1"

    @pytest.mark.asyncio
    async def test_should_call_repository_with_correct_series_id(self) -> None:
        mocks = make_media_uow_mock()
        mocks.series.delete.return_value = True
        use_case = DeleteSeriesUseCase(uow_factory=mocks.factory)

        await use_case.execute(DeleteSeriesInput(series_id="ser_abc123def456"))

        call_arg = mocks.series.delete.call_args[0][0]
        assert str(call_arg) == "ser_abc123def456"
