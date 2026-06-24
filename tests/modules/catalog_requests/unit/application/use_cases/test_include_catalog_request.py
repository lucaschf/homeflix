"""Tests for ``IncludeCatalogRequestUseCase``."""

from unittest.mock import AsyncMock

import pytest

from src.building_blocks.application.errors import ResourceNotFoundException
from src.modules.catalog_requests.application.dtos import IncludeCatalogRequestInput
from src.modules.catalog_requests.application.ports import NotificationPublisherPort
from src.modules.catalog_requests.application.use_cases import (
    IncludeCatalogRequestUseCase,
)
from src.modules.catalog_requests.domain.entities import (
    CatalogRequest,
    CatalogSubscription,
)
from src.shared_kernel.value_objects import MediaType
from tests.modules.catalog_requests.unit.conftest import (
    make_catalog_requests_uow_mock,
)


def _pending() -> CatalogRequest:
    return CatalogRequest.create(tmdb_id=348, media_type=MediaType.MOVIE, title="Alien")


@pytest.mark.unit
class TestIncludeCatalogRequestUseCase:
    """Tests for the admin "mark as included" action."""

    @pytest.mark.asyncio
    async def test_fulfills_and_fans_out_without_media_id(self) -> None:
        request = _pending()
        mocks = make_catalog_requests_uow_mock()
        mocks.catalog_requests.find_by_id.return_value = request
        mocks.catalog_requests.update.side_effect = lambda req: req
        mocks.catalog_subscriptions.list_for_request.return_value = [
            CatalogSubscription.create(request.id, "usr_alice"),
            CatalogSubscription.create(request.id, "usr_bob"),
        ]
        publisher = AsyncMock(spec=NotificationPublisherPort)
        use_case = IncludeCatalogRequestUseCase(
            uow_factory=mocks.factory,
            notification_publisher=publisher,
        )

        result = await use_case.execute(IncludeCatalogRequestInput(request_id=str(request.id)))

        assert result.is_fulfilled is True
        mocks.catalog_requests.update.assert_called_once()
        assert publisher.publish_catalog_arrival.await_count == 2
        payload = publisher.publish_catalog_arrival.await_args_list[0].args[0]
        assert payload.media_id is None
        assert payload.title == "Alien"

    @pytest.mark.asyncio
    async def test_raises_404_when_not_found(self) -> None:
        mocks = make_catalog_requests_uow_mock()
        mocks.catalog_requests.find_by_id.return_value = None
        use_case = IncludeCatalogRequestUseCase(uow_factory=mocks.factory)

        with pytest.raises(ResourceNotFoundException):
            await use_case.execute(IncludeCatalogRequestInput(request_id="req_missing00000"))

    @pytest.mark.asyncio
    async def test_idempotent_when_already_fulfilled(self) -> None:
        request = _pending().mark_fulfilled()
        mocks = make_catalog_requests_uow_mock()
        mocks.catalog_requests.find_by_id.return_value = request
        publisher = AsyncMock(spec=NotificationPublisherPort)
        use_case = IncludeCatalogRequestUseCase(
            uow_factory=mocks.factory,
            notification_publisher=publisher,
        )

        result = await use_case.execute(IncludeCatalogRequestInput(request_id=str(request.id)))

        assert result.is_fulfilled is True
        mocks.catalog_requests.update.assert_not_called()
        publisher.publish_catalog_arrival.assert_not_called()

    @pytest.mark.asyncio
    async def test_fulfills_without_publisher(self) -> None:
        request = _pending()
        mocks = make_catalog_requests_uow_mock()
        mocks.catalog_requests.find_by_id.return_value = request
        mocks.catalog_requests.update.side_effect = lambda req: req
        use_case = IncludeCatalogRequestUseCase(uow_factory=mocks.factory)

        result = await use_case.execute(IncludeCatalogRequestInput(request_id=str(request.id)))

        assert result.is_fulfilled is True
        mocks.catalog_requests.update.assert_called_once()
        mocks.catalog_subscriptions.list_for_request.assert_not_called()
