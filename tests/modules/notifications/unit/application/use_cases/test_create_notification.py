"""Tests for ``CreateNotificationUseCase``."""

import pytest

from src.modules.notifications.application.dtos import CreateNotificationInput
from src.modules.notifications.application.use_cases import CreateNotificationUseCase
from src.modules.notifications.domain.value_objects import NotificationKind
from tests.modules.notifications.unit.conftest import make_notifications_uow_mock


@pytest.mark.unit
class TestCreateNotificationUseCase:
    """Tests for the "create one notification row" handler."""

    @pytest.mark.asyncio
    async def test_persists_notification(self) -> None:
        mocks = make_notifications_uow_mock()
        mocks.notifications.add.side_effect = lambda n: n
        use_case = CreateNotificationUseCase(uow_factory=mocks.factory)

        result = await use_case.execute(
            CreateNotificationInput(
                recipient_user_id="usr_alice0000000",
                kind=NotificationKind.CATALOG_REQUEST_FULFILLED,
                title="Alien chegou ao catálogo",
                payload={
                    "tmdb_id": 348,
                    "media_id": "mov_abc",
                    "media_type": "movie",
                },
            ),
        )

        assert result.recipient_user_id == "usr_alice0000000"
        assert result.kind == "catalog_request_fulfilled"
        assert result.title == "Alien chegou ao catálogo"
        assert result.payload["tmdb_id"] == 348
        assert result.is_read is False
        mocks.notifications.add.assert_awaited_once()
