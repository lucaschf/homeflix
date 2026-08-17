"""Tests for ``NotificationPublisherAdapter``."""

from unittest.mock import AsyncMock

import pytest

from src.modules.catalog_requests.application.ports import CatalogArrivalNotification
from src.modules.notifications.application.dtos import CreateNotificationInput
from src.modules.notifications.application.use_cases import CreateNotificationUseCase
from src.modules.notifications.domain.value_objects import NotificationKind
from src.modules.notifications.infrastructure.acl import NotificationPublisherAdapter
from src.shared_kernel.value_objects.media_id import MovieId


@pytest.mark.unit
class TestNotificationPublisherAdapter:
    """Tests for the cross-BC publisher adapter."""

    @pytest.mark.asyncio
    async def test_translates_arrival_into_create_input(self) -> None:
        create_uc = AsyncMock(spec=CreateNotificationUseCase)
        adapter = NotificationPublisherAdapter(create_notification=create_uc)

        await adapter.publish_catalog_arrival(
            CatalogArrivalNotification(
                recipient_user_id="usr_alice0000000",
                title="Alien",
                tmdb_id=348,
                media_id=MovieId("mov_abcabcabcabc"),
                media_type="movie",
            ),
        )

        create_uc.execute.assert_awaited_once()
        called_input = create_uc.execute.await_args.args[0]
        assert isinstance(called_input, CreateNotificationInput)
        assert called_input.recipient_user_id == "usr_alice0000000"
        assert called_input.kind == NotificationKind.CATALOG_REQUEST_FULFILLED
        assert called_input.title == "Alien"
        assert called_input.payload == {
            "tmdb_id": 348,
            "media_id": "mov_abcabcabcabc",
            "media_type": "movie",
        }
