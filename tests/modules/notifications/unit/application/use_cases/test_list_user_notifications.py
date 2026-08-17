"""Tests for ``ListUserNotificationsUseCase``."""

import pytest

from src.modules.notifications.application.dtos import ListUserNotificationsInput
from src.modules.notifications.application.use_cases import ListUserNotificationsUseCase
from src.modules.notifications.domain.entities import Notification
from src.modules.notifications.domain.value_objects import NotificationKind
from tests.modules.notifications.unit.conftest import make_notifications_uow_mock


def _make_notification(title: str = "Alien") -> Notification:
    return Notification.create(
        recipient_user_id="usr_alice0000000",
        kind=NotificationKind.CATALOG_REQUEST_FULFILLED,
        title=title,
    )


@pytest.mark.unit
class TestListUserNotificationsUseCase:
    """Tests for the inbox listing."""

    @pytest.mark.asyncio
    async def test_returns_items_and_unread_count(self) -> None:
        rows = [_make_notification("Alien"), _make_notification("Aliens")]
        mocks = make_notifications_uow_mock()
        mocks.notifications.list_for_user.return_value = rows
        mocks.notifications.count_unread_for_user.return_value = 2
        use_case = ListUserNotificationsUseCase(uow_factory=mocks.factory)

        result = await use_case.execute(
            ListUserNotificationsInput(recipient_user_id="usr_alice0000000"),
        )

        assert len(result.items) == 2
        assert result.unread_count == 2
        mocks.notifications.list_for_user.assert_awaited_once_with(
            recipient_user_id="usr_alice0000000",
            unread_only=False,
            limit=50,
        )

    @pytest.mark.asyncio
    async def test_passes_unread_only_filter(self) -> None:
        mocks = make_notifications_uow_mock()
        mocks.notifications.list_for_user.return_value = []
        mocks.notifications.count_unread_for_user.return_value = 0
        use_case = ListUserNotificationsUseCase(uow_factory=mocks.factory)

        await use_case.execute(
            ListUserNotificationsInput(
                recipient_user_id="usr_alice0000000",
                unread_only=True,
                limit=10,
            ),
        )

        mocks.notifications.list_for_user.assert_awaited_once_with(
            recipient_user_id="usr_alice0000000",
            unread_only=True,
            limit=10,
        )

    @pytest.mark.asyncio
    async def test_unread_count_independent_of_filter(self) -> None:
        """The badge stays accurate even when the dropdown only shows
        the read page — verifying the count comes from a dedicated
        repo call, not ``len(items)``."""
        mocks = make_notifications_uow_mock()
        mocks.notifications.list_for_user.return_value = []  # filtered out
        mocks.notifications.count_unread_for_user.return_value = 3
        use_case = ListUserNotificationsUseCase(uow_factory=mocks.factory)

        result = await use_case.execute(
            ListUserNotificationsInput(
                recipient_user_id="usr_alice0000000",
                unread_only=False,
            ),
        )

        assert result.items == []
        assert result.unread_count == 3
