"""Tests for ``ListAdminCatalogRequestsUseCase``."""

import pytest

from src.modules.catalog_requests.application.use_cases import (
    ListAdminCatalogRequestsUseCase,
)
from src.modules.catalog_requests.domain.entities import CatalogRequest
from src.shared_kernel.value_objects import MediaType
from tests.modules.catalog_requests.unit.conftest import (
    make_catalog_requests_uow_mock,
)


@pytest.mark.unit
class TestListAdminCatalogRequestsUseCase:
    """Tests for the admin queue listing."""

    @pytest.mark.asyncio
    async def test_enriches_with_subscriber_count(self) -> None:
        a = CatalogRequest.create(tmdb_id=1, media_type=MediaType.MOVIE)
        b = CatalogRequest.create(tmdb_id=2, media_type=MediaType.MOVIE)
        mocks = make_catalog_requests_uow_mock()
        mocks.catalog_requests.list_pending.return_value = [a, b]
        mocks.catalog_subscriptions.count_by_requests.return_value = {a.id: 5}
        use_case = ListAdminCatalogRequestsUseCase(uow_factory=mocks.factory)

        items = await use_case.execute()

        by_tmdb = {item.request.tmdb_id: item for item in items}
        assert by_tmdb[1].subscriber_count == 5
        assert by_tmdb[2].subscriber_count == 0
        mocks.catalog_requests.list_pending.assert_awaited_once_with(None)
