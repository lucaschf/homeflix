"""Tests for ``ListCatalogRequestFeedUseCase``."""

import pytest

from src.modules.catalog_requests.application.use_cases import (
    ListCatalogRequestFeedUseCase,
)
from src.modules.catalog_requests.application.use_cases.list_catalog_request_feed import (
    ListCatalogRequestFeedInput,
)
from src.modules.catalog_requests.domain.entities import CatalogRequest
from src.shared_kernel.value_objects import MediaType
from tests.modules.catalog_requests.unit.conftest import (
    make_catalog_requests_uow_mock,
)


@pytest.mark.unit
class TestListCatalogRequestFeedUseCase:
    """Tests for the member 'Em breve' feed."""

    @pytest.mark.asyncio
    async def test_enriches_with_count_and_subscription(self) -> None:
        followed = CatalogRequest.create(tmdb_id=1, media_type=MediaType.MOVIE)
        other = CatalogRequest.create(tmdb_id=2, media_type=MediaType.MOVIE)
        mocks = make_catalog_requests_uow_mock()
        mocks.catalog_requests.list_pending.return_value = [followed, other]
        mocks.catalog_subscriptions.count_by_requests.return_value = {followed.id: 3}
        mocks.catalog_subscriptions.request_ids_for_user.return_value = {followed.id}
        use_case = ListCatalogRequestFeedUseCase(uow_factory=mocks.factory)

        items = await use_case.execute(ListCatalogRequestFeedInput(user_id="usr_me"))

        by_tmdb = {item.request.tmdb_id: item for item in items}
        assert by_tmdb[1].subscriber_count == 3
        assert by_tmdb[1].is_subscribed is True
        # Absent from the count map → 0; not in the caller's set → False.
        assert by_tmdb[2].subscriber_count == 0
        assert by_tmdb[2].is_subscribed is False

    @pytest.mark.asyncio
    async def test_passes_collection_scope_through(self) -> None:
        mocks = make_catalog_requests_uow_mock()
        mocks.catalog_requests.list_pending.return_value = []
        use_case = ListCatalogRequestFeedUseCase(uow_factory=mocks.factory)

        result = await use_case.execute(
            ListCatalogRequestFeedInput(user_id="usr_me", collection_tmdb_id=8091),
        )

        assert result == []
        mocks.catalog_requests.list_pending.assert_awaited_once_with(8091)
