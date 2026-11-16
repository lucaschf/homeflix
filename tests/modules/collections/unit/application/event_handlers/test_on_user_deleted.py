"""Tests for OnUserDeletedHandler follow/list cleanup."""

import pytest
from structlog.testing import capture_logs
from tests.modules.collections.unit.conftest import make_collections_uow_mock

from src.modules.collections.application.event_handlers import OnUserDeletedHandler
from src.shared_kernel.integration_events import UserDeletedEvent


@pytest.mark.unit
class TestOnUserDeletedHandler:
    """The handler wipes watchlist, custom lists, and follows."""

    @pytest.mark.asyncio
    async def test_drops_watchlist_lists_and_follows(self) -> None:
        mocks = make_collections_uow_mock()
        mocks.watchlist.delete_all_for_profiles.return_value = 1
        mocks.custom_lists.delete_all_for_profiles.return_value = 2
        mocks.list_follows.delete_all_for_followers.return_value = 3
        handler = OnUserDeletedHandler(uow_factory=mocks.factory)

        await handler.handle(
            UserDeletedEvent(user_id="usr_abc123def456", profile_ids=("prf_test12345678",))
        )

        mocks.watchlist.delete_all_for_profiles.assert_awaited_once_with(["prf_test12345678"])
        mocks.custom_lists.delete_all_for_profiles.assert_awaited_once_with(["prf_test12345678"])
        mocks.list_follows.delete_all_for_followers.assert_awaited_once_with(["prf_test12345678"])

    @pytest.mark.asyncio
    async def test_ignores_events_without_profiles(self) -> None:
        mocks = make_collections_uow_mock()
        handler = OnUserDeletedHandler(uow_factory=mocks.factory)

        await handler.handle(UserDeletedEvent(user_id="usr_abc123def456", profile_ids=()))

        mocks.list_follows.delete_all_for_followers.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_logs_the_cleanup_as_a_structured_event(self) -> None:
        mocks = make_collections_uow_mock()
        mocks.watchlist.delete_all_for_profiles.return_value = 1
        mocks.custom_lists.delete_all_for_profiles.return_value = 2
        mocks.list_follows.delete_all_for_followers.return_value = 3

        with capture_logs() as logs:
            await OnUserDeletedHandler(uow_factory=mocks.factory).handle(
                UserDeletedEvent(user_id="usr_abc123def456", profile_ids=("prf_test12345678",))
            )

        assert logs == [
            {
                "event": "Collections cleared for deleted user",
                "log_level": "info",
                "handler": "OnUserDeletedHandler",
                "watchlist_deleted": 1,
                "lists_deleted": 2,
                "follows_deleted": 3,
                "user_id": "usr_abc123def456",
                "profile_count": 1,
            }
        ]
