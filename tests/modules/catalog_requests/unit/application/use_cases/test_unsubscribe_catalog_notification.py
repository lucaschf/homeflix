"""Tests for ``UnsubscribeCatalogNotificationUseCase``."""

import pytest

from src.modules.catalog_requests.application.dtos import (
    UnsubscribeCatalogNotificationInput,
)
from src.modules.catalog_requests.application.use_cases import (
    UnsubscribeCatalogNotificationUseCase,
)
from src.modules.catalog_requests.domain.entities import CatalogRequest
from src.shared_kernel.value_objects import MediaType
from tests.modules.catalog_requests.unit.conftest import (
    make_catalog_requests_uow_mock,
)


def _input(user_id: str = "usr_alice") -> UnsubscribeCatalogNotificationInput:
    return UnsubscribeCatalogNotificationInput(
        tmdb_id=348,
        media_type=MediaType.MOVIE,
        user_id=user_id,
    )


@pytest.mark.unit
class TestUnsubscribeCatalogNotificationUseCase:
    """Tests for the "desligar o aviso" handler."""

    @pytest.mark.asyncio
    async def test_returns_none_when_no_request(self) -> None:
        mocks = make_catalog_requests_uow_mock()
        mocks.catalog_requests.find_by_tmdb_id.return_value = None
        use_case = UnsubscribeCatalogNotificationUseCase(uow_factory=mocks.factory)

        result = await use_case.execute(_input())

        assert result is None
        mocks.catalog_subscriptions.remove.assert_not_called()

    @pytest.mark.asyncio
    async def test_removes_the_callers_subscription(self) -> None:
        existing = CatalogRequest.create(
            tmdb_id=348,
            media_type=MediaType.MOVIE,
            notify_on_arrival=True,
        )
        mocks = make_catalog_requests_uow_mock()
        mocks.catalog_requests.find_by_tmdb_id.return_value = existing
        mocks.catalog_subscriptions.count_for_request.return_value = 1  # others remain
        use_case = UnsubscribeCatalogNotificationUseCase(uow_factory=mocks.factory)

        await use_case.execute(_input("usr_alice"))

        mocks.catalog_subscriptions.remove.assert_awaited_once_with(
            existing.id,
            "usr_alice",
        )

    @pytest.mark.asyncio
    async def test_keeps_flag_on_when_other_subscribers_remain(self) -> None:
        existing = CatalogRequest.create(
            tmdb_id=348,
            media_type=MediaType.MOVIE,
            notify_on_arrival=True,
        )
        mocks = make_catalog_requests_uow_mock()
        mocks.catalog_requests.find_by_tmdb_id.return_value = existing
        mocks.catalog_subscriptions.count_for_request.return_value = 2
        use_case = UnsubscribeCatalogNotificationUseCase(uow_factory=mocks.factory)

        result = await use_case.execute(_input())

        # Flag already matches reality (has subscribers) → no rewrite.
        mocks.catalog_requests.update.assert_not_called()
        assert result is not None
        assert result.notify_on_arrival is True

    @pytest.mark.asyncio
    async def test_clears_flag_when_last_subscriber_leaves(self) -> None:
        existing = CatalogRequest.create(
            tmdb_id=348,
            media_type=MediaType.MOVIE,
            notify_on_arrival=True,
        )
        mocks = make_catalog_requests_uow_mock()
        mocks.catalog_requests.find_by_tmdb_id.return_value = existing
        mocks.catalog_requests.update.side_effect = lambda req: req
        mocks.catalog_subscriptions.count_for_request.return_value = 0
        use_case = UnsubscribeCatalogNotificationUseCase(uow_factory=mocks.factory)

        result = await use_case.execute(_input())

        mocks.catalog_requests.update.assert_called_once()
        updated = mocks.catalog_requests.update.await_args.args[0]
        assert updated.notify_on_arrival is False
        assert result is not None
        assert result.notify_on_arrival is False
