"""Tests for ``MarkNotificationReadUseCase``."""

import pytest

from src.building_blocks.application.errors import ResourceNotFoundException
from src.modules.notifications.application.dtos import MarkNotificationReadInput
from src.modules.notifications.application.use_cases import MarkNotificationReadUseCase
from src.modules.notifications.domain.entities import Notification
from src.modules.notifications.domain.value_objects import NotificationKind
from tests.modules.notifications.unit.conftest import make_notifications_uow_mock


def _make_notification() -> Notification:
    return Notification.create(
        recipient_user_id="usr_alice0000000",
        kind=NotificationKind.CATALOG_REQUEST_FULFILLED,
        title="Alien",
    )


@pytest.mark.unit
class TestMarkNotificationReadUseCase:
    """Tests for the "mark notification read" handler."""

    @pytest.mark.asyncio
    async def test_marks_as_read(self) -> None:
        existing = _make_notification()
        mocks = make_notifications_uow_mock()
        mocks.notifications.find_by_id_for_user.return_value = existing
        mocks.notifications.update.side_effect = lambda n: n
        use_case = MarkNotificationReadUseCase(uow_factory=mocks.factory)

        result = await use_case.execute(
            MarkNotificationReadInput(
                notification_id=str(existing.id),
                recipient_user_id="usr_alice0000000",
            ),
        )

        assert result.is_read is True
        assert result.read_at is not None
        mocks.notifications.update.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_short_circuits_when_already_read(self) -> None:
        """Click-spamming the bell must not generate spurious writes."""
        existing = _make_notification().mark_read()
        mocks = make_notifications_uow_mock()
        mocks.notifications.find_by_id_for_user.return_value = existing
        use_case = MarkNotificationReadUseCase(uow_factory=mocks.factory)

        result = await use_case.execute(
            MarkNotificationReadInput(
                notification_id=str(existing.id),
                recipient_user_id="usr_alice0000000",
            ),
        )

        assert result.is_read is True
        mocks.notifications.update.assert_not_called()

    @pytest.mark.asyncio
    async def test_raises_when_not_found_for_user(self) -> None:
        """Cross-user lookups (or plain missing rows) raise
        ``ResourceNotFoundException`` rather than leaking a permission
        oracle on which ids belong to which users."""
        mocks = make_notifications_uow_mock()
        mocks.notifications.find_by_id_for_user.return_value = None
        use_case = MarkNotificationReadUseCase(uow_factory=mocks.factory)

        with pytest.raises(ResourceNotFoundException):
            await use_case.execute(
                MarkNotificationReadInput(
                    notification_id="nfy_abcdefghij12",
                    recipient_user_id="usr_bob000000000",
                ),
            )
