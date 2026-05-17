"""Tests for DismissCatalogRequestUseCase."""

import pytest

from src.building_blocks.application.errors import ResourceNotFoundException
from src.modules.catalog_requests.application.dtos import DismissCatalogRequestInput
from src.modules.catalog_requests.application.use_cases import (
    DismissCatalogRequestUseCase,
)
from src.modules.catalog_requests.domain.value_objects import CatalogRequestId
from tests.modules.catalog_requests.unit.conftest import (
    make_catalog_requests_uow_mock,
)


class TestDismissCatalogRequestUseCase:
    """Tests for the admin dismiss flow — soft-delete by external id."""

    @pytest.mark.asyncio
    async def test_should_soft_delete_when_request_exists(self) -> None:
        mocks = make_catalog_requests_uow_mock()
        mocks.catalog_requests.delete.return_value = True
        use_case = DismissCatalogRequestUseCase(uow_factory=mocks.factory)

        await use_case.execute(DismissCatalogRequestInput(request_id="req_abc123def456"))

        mocks.catalog_requests.delete.assert_awaited_once()
        passed = mocks.catalog_requests.delete.await_args.args[0]
        assert isinstance(passed, CatalogRequestId)
        assert str(passed) == "req_abc123def456"

    @pytest.mark.asyncio
    async def test_should_raise_not_found_when_request_missing(self) -> None:
        mocks = make_catalog_requests_uow_mock()
        mocks.catalog_requests.delete.return_value = False
        use_case = DismissCatalogRequestUseCase(uow_factory=mocks.factory)

        with pytest.raises(ResourceNotFoundException) as exc_info:
            await use_case.execute(
                DismissCatalogRequestInput(request_id="req_missing00000"),
            )

        assert exc_info.value.resource_type == "CatalogRequest"
        assert exc_info.value.resource_id == "req_missing00000"
