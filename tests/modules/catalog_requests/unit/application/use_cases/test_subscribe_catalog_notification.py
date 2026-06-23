"""Tests for ``SubscribeCatalogNotificationUseCase``."""

import pytest

from src.modules.catalog_requests.application.dtos import (
    SubscribeCatalogNotificationInput,
)
from src.modules.catalog_requests.application.use_cases import (
    SubscribeCatalogNotificationUseCase,
)
from src.modules.catalog_requests.domain.entities import (
    CatalogRequest,
    CatalogSubscription,
)
from src.shared_kernel.value_objects import MediaType
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
                media_type=MediaType.MOVIE,
                collection_tmdb_id=8091,
            ),
        )

        assert result.notify_on_arrival is True
        mocks.catalog_requests.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_flips_existing_notify_off_to_on(self) -> None:
        existing = CatalogRequest.create(
            tmdb_id=348,
            media_type=MediaType.MOVIE,
        )
        mocks = make_catalog_requests_uow_mock()
        mocks.catalog_requests.find_by_tmdb_id.return_value = existing
        mocks.catalog_requests.update.side_effect = lambda req: req
        use_case = SubscribeCatalogNotificationUseCase(uow_factory=mocks.factory)

        result = await use_case.execute(
            SubscribeCatalogNotificationInput(
                tmdb_id=348,
                media_type=MediaType.MOVIE,
            ),
        )

        assert result.notify_on_arrival is True
        mocks.catalog_requests.update.assert_called_once()

    @pytest.mark.asyncio
    async def test_short_circuits_when_already_subscribed(self) -> None:
        existing = CatalogRequest.create(
            tmdb_id=348,
            media_type=MediaType.MOVIE,
            notify_on_arrival=True,
        )
        mocks = make_catalog_requests_uow_mock()
        mocks.catalog_requests.find_by_tmdb_id.return_value = existing
        use_case = SubscribeCatalogNotificationUseCase(uow_factory=mocks.factory)

        result = await use_case.execute(
            SubscribeCatalogNotificationInput(
                tmdb_id=348,
                media_type=MediaType.MOVIE,
            ),
        )

        assert result.notify_on_arrival is True
        mocks.catalog_requests.update.assert_not_called()
        mocks.catalog_requests.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_creates_subscription_for_the_requester(self) -> None:
        existing = CatalogRequest.create(
            tmdb_id=348,
            media_type=MediaType.MOVIE,
            requester_user_id="usr_alice",
            notify_on_arrival=True,
        )
        mocks = make_catalog_requests_uow_mock()
        mocks.catalog_requests.find_by_tmdb_id.return_value = existing
        mocks.catalog_requests.update.side_effect = lambda req: req
        mocks.catalog_subscriptions.find.return_value = None
        use_case = SubscribeCatalogNotificationUseCase(uow_factory=mocks.factory)

        await use_case.execute(
            SubscribeCatalogNotificationInput(
                tmdb_id=348,
                media_type=MediaType.MOVIE,
                requester_user_id="usr_alice",
            ),
        )

        mocks.catalog_subscriptions.add.assert_awaited_once()
        added = mocks.catalog_subscriptions.add.await_args.args[0]
        assert added.user_id == "usr_alice"
        assert added.request_id == existing.id

    @pytest.mark.asyncio
    async def test_subscription_is_idempotent(self) -> None:
        existing = CatalogRequest.create(
            tmdb_id=348,
            media_type=MediaType.MOVIE,
            requester_user_id="usr_alice",
            notify_on_arrival=True,
        )
        mocks = make_catalog_requests_uow_mock()
        mocks.catalog_requests.find_by_tmdb_id.return_value = existing
        mocks.catalog_subscriptions.find.return_value = CatalogSubscription.create(
            existing.id,
            "usr_alice",
        )
        use_case = SubscribeCatalogNotificationUseCase(uow_factory=mocks.factory)

        await use_case.execute(
            SubscribeCatalogNotificationInput(
                tmdb_id=348,
                media_type=MediaType.MOVIE,
                requester_user_id="usr_alice",
            ),
        )

        mocks.catalog_subscriptions.add.assert_not_called()
