"""Tests for ``MarkAllNotificationsReadUseCase``."""

import pytest

from src.modules.notifications.application.dtos import MarkAllNotificationsReadInput
from src.modules.notifications.application.use_cases import (
    MarkAllNotificationsReadUseCase,
)
from tests.modules.notifications.unit.conftest import make_notifications_uow_mock


@pytest.mark.unit
class TestMarkAllNotificationsReadUseCase:
    """Tests for the bulk-clear handler."""

    @pytest.mark.asyncio
    async def test_returns_count_of_flipped_rows(self) -> None:
        mocks = make_notifications_uow_mock()
        mocks.notifications.mark_all_read_for_user.return_value = 4
        use_case = MarkAllNotificationsReadUseCase(uow_factory=mocks.factory)

        result = await use_case.execute(
            MarkAllNotificationsReadInput(recipient_user_id="usr_alice0000000"),
        )

        assert result.marked_read == 4
        mocks.notifications.mark_all_read_for_user.assert_awaited_once_with(
            "usr_alice0000000",
        )

    @pytest.mark.asyncio
    async def test_idempotent_empty_inbox(self) -> None:
        """An already-clean inbox returns ``marked_read=0`` without
        any need for the caller to branch on the empty case."""
        mocks = make_notifications_uow_mock()
        mocks.notifications.mark_all_read_for_user.return_value = 0
        use_case = MarkAllNotificationsReadUseCase(uow_factory=mocks.factory)

        result = await use_case.execute(
            MarkAllNotificationsReadInput(recipient_user_id="usr_alice0000000"),
        )

        assert result.marked_read == 0
