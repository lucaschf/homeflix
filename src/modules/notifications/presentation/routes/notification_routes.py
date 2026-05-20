"""Notifications REST API routes."""

from dataclasses import asdict
from typing import Any

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Query

from src.building_blocks.presentation import api_list, api_single
from src.config.containers import ApplicationContainer
from src.modules.identity.infrastructure.auth import current_active_user
from src.modules.identity.infrastructure.persistence.models.user_model import UserModel
from src.modules.notifications.application.dtos import (
    ListUserNotificationsInput,
    MarkNotificationReadInput,
)
from src.modules.notifications.application.use_cases import (
    ListUserNotificationsUseCase,
    MarkNotificationReadUseCase,
)

router = APIRouter(prefix="/api/v1/notifications", tags=["Notifications"])


@router.get("")  # type: ignore[misc]
@inject  # type: ignore[misc]
async def list_user_notifications(
    user: UserModel = Depends(current_active_user),
    unread_only: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    use_case: ListUserNotificationsUseCase = Depends(
        Provide[ApplicationContainer.notifications.list_user_notifications],
    ),
) -> dict[str, Any]:
    """List the caller's notifications, newest first.

    The ``unread_count`` field on the response metadata is
    independent of the filter so the header bell renders the
    badge correctly even when the dropdown is showing the read
    page. Scoped to the authenticated user by construction — the
    route forwards ``user.external_id`` to the use case and the
    repository scopes every read on that field.
    """
    result = await use_case.execute(
        ListUserNotificationsInput(
            recipient_user_id=user.external_id,
            unread_only=unread_only,
            limit=limit,
        ),
    )
    return api_list(
        [asdict(item) for item in result.items],
        metadata_extras={"unread_count": result.unread_count},
    )


@router.patch("/{notification_id}/read")  # type: ignore[misc]
@inject  # type: ignore[misc]
async def mark_notification_read(
    notification_id: str,
    user: UserModel = Depends(current_active_user),
    use_case: MarkNotificationReadUseCase = Depends(
        Provide[ApplicationContainer.notifications.mark_notification_read],
    ),
) -> dict[str, Any]:
    """Mark a single notification as read.

    Scoped on the caller: the use case loads the row constrained
    by both ``notification_id`` and ``user.external_id`` so a
    user can't mark another user's notification read just by
    guessing the id. Idempotent — re-marking an already-read row
    returns the existing state without a DB write.
    """
    result = await use_case.execute(
        MarkNotificationReadInput(
            notification_id=notification_id,
            recipient_user_id=user.external_id,
        ),
    )
    return api_single("notification", asdict(result))


__all__ = ["router"]
