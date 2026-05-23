"""Admin REST API for the media-conflict queue (ADR-015 Phase 1).

Read-only surface for ``/api/v1/admin/conflicts``: lists pending
content-identity collisions detected by the post-enrich hook so the
operator can decide how to resolve them. Resolution endpoints land
in Phase 2.
"""

from dataclasses import asdict
from typing import Any

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Query

from src.building_blocks.application.pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from src.building_blocks.presentation import api_list
from src.building_blocks.presentation.responses import Pagination
from src.config.containers import ApplicationContainer
from src.modules.identity.infrastructure.auth import current_admin_user
from src.modules.identity.infrastructure.persistence.models.user_model import UserModel
from src.modules.media.application.dtos.conflict_dtos import ListConflictsInput
from src.modules.media.application.use_cases.list_conflicts import ListConflictsUseCase

router = APIRouter(prefix="/api/v1/admin/conflicts", tags=["Admin — Conflicts"])


@router.get("")
@inject
async def list_admin_conflicts(
    cursor: str | None = Query(default=None),
    limit: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    _admin: UserModel = Depends(current_admin_user),
    use_case: ListConflictsUseCase = Depends(
        Provide[ApplicationContainer.media.list_conflicts],
    ),
) -> dict[str, Any]:
    """Return the next page of pending content-identity conflicts.

    Items are newest-first. Each item embeds title + year projections
    for both sides so the admin UI does not need an extra round-trip
    to render the queue row.
    """
    output = await use_case.execute(
        ListConflictsInput(cursor=cursor, limit=limit),
    )
    return api_list(
        [asdict(item) for item in output.items],
        pagination=Pagination(
            has_more=output.has_more,
            next_cursor=output.next_cursor,
        ),
    )


__all__ = ["router"]
