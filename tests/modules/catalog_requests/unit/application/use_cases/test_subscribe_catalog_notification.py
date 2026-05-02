"""Tests for ``SubscribeCatalogNotificationUseCase``."""

import pytest

from src.modules.catalog_requests.application.dtos import (
    SubscribeCatalogNotificationInput,
)
from src.modules.catalog_requests.application.use_cases import (
    SubscribeCatalogNotificationUseCase,
)
from src.modules.catalog_requests.domain.entities import CatalogRequest
from src.modules.catalog_requests.domain.value_objects import RequestedMediaType
from tests.modules.catalog_requests.unit.conftest import (
    make_catalog_requests_uow_mock,
)


@pytest.mark.unit
class TestSubscribeCatalogNotificationUseCase:
    """Tests for the "Avisar quando chegar" handler."""

    @pytest.mark.asyncio
    async def test_creates_request_with_notify_when_none_exists(self) -> None:
        mocks = make_catalog_requests_uow_mock()
        mocks.catalog_requests.find_by_tmdb_id.return_value = None
        mocks.catalog_requests.add.side_effect = lambda req: req
        use_case = SubscribeCatalogNotificationUseCase(uow_factory=mocks.factory)

        result = await use_case.execute(
            SubscribeCatalogNotificationInput(
                tmdb_id=348,
                media_type=RequestedMediaType.MOVIE,
                collection_tmdb_id=8091,
            ),
        )

        assert result.notify_on_arrival is True
        mocks.catalog_requests.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_flips_existing_notify_off_to_on(self) -> None:
        existing = CatalogRequest.create(
            tmdb_id=348,
            media_type=RequestedMediaType.MOVIE,
        )
        mocks = make_catalog_requests_uow_mock()
        mocks.catalog_requests.find_by_tmdb_id.return_value = existing
        mocks.catalog_requests.update.side_effect = lambda req: req
        use_case = SubscribeCatalogNotificationUseCase(uow_factory=mocks.factory)

        result = await use_case.execute(
            SubscribeCatalogNotificationInput(
                tmdb_id=348,
                media_type=RequestedMediaType.MOVIE,
            ),
        )

        assert result.notify_on_arrival is True
        mocks.catalog_requests.update.assert_called_once()

    @pytest.mark.asyncio
    async def test_short_circuits_when_already_subscribed(self) -> None:
        existing = CatalogRequest.create(
            tmdb_id=348,
            media_type=RequestedMediaType.MOVIE,
            notify_on_arrival=True,
        )
        mocks = make_catalog_requests_uow_mock()
        mocks.catalog_requests.find_by_tmdb_id.return_value = existing
        use_case = SubscribeCatalogNotificationUseCase(uow_factory=mocks.factory)

        result = await use_case.execute(
            SubscribeCatalogNotificationInput(
                tmdb_id=348,
                media_type=RequestedMediaType.MOVIE,
            ),
        )

        assert result.notify_on_arrival is True
        mocks.catalog_requests.update.assert_not_called()
        mocks.catalog_requests.add.assert_not_called()
