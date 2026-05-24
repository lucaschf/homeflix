"""Admin REST API for the media-conflict queue (ADR-015).

``GET /?state=pending`` (default) lists content-identity collisions
queued by the post-enrich hook for operator triage (Phase 1).
``GET /?state=resolved&source=auto`` powers the audit view for
Phase 3 silent auto-merges; ``source=manual`` shows admin decisions.
``POST /{id}/resolve`` applies the operator's chosen disposition
(Phase 2): mark-distinct, merge-keep-both, or merge-replace.
"""

from dataclasses import asdict
from typing import Any, Literal

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Path, Query
from pydantic import BaseModel, Field

from src.building_blocks.application.pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from src.building_blocks.presentation import api_list, api_single
from src.building_blocks.presentation.responses import Pagination
from src.config.containers import ApplicationContainer
from src.modules.identity.infrastructure.auth import current_admin_user
from src.modules.identity.infrastructure.persistence.models.user_model import UserModel
from src.modules.media.application.dtos.conflict_dtos import (
    ListConflictsInput,
    ResolveMediaConflictInput,
)
from src.modules.media.application.use_cases.list_conflicts import ListConflictsUseCase
from src.modules.media.application.use_cases.resolve_media_conflict import (
    ResolveMediaConflictUseCase,
)
from src.modules.media.domain.entities.media_conflict import ResolutionAction


class ResolveConflictBody(BaseModel):
    """Request body for ``POST /admin/conflicts/{id}/resolve``.

    Pydantic validates the action enum + the winner_id format
    (string, length-bounded to match the external id contract) before
    the use case runs; the aggregate's invariants (winner must be one
    of the candidates, MARK_DISTINCT forbids winner_id) surface as
    422 via the standard domain → HTTP mapping.
    """

    action: ResolutionAction = Field(
        ...,
        description="Resolution disposition picked by the operator.",
    )
    winner_id: str | None = Field(
        default=None,
        description=(
            "External id of the surviving candidate. Required for "
            "merge_keep_both / merge_replace; forbidden for "
            "mark_distinct."
        ),
        max_length=50,
    )


router = APIRouter(prefix="/api/v1/admin/conflicts", tags=["Admin — Conflicts"])


@router.get("")
@inject
async def list_admin_conflicts(
    state: Literal["pending", "resolved"] = Query(default="pending"),
    source: Literal["manual", "auto"] | None = Query(default=None),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    _admin: UserModel = Depends(current_admin_user),
    use_case: ListConflictsUseCase = Depends(
        Provide[ApplicationContainer.media.list_conflicts],
    ),
) -> dict[str, Any]:
    """Return the next page of conflicts matching ``state`` (+ ``source``).

    - ``state=pending`` (default): the operator queue — rows that
      still need a decision.
    - ``state=resolved``: audit view of closed rows. Combine with
      ``source=manual`` (admin) or ``source=auto`` (Phase 3 silent
      merge of orphans); omit ``source`` to see both.

    Items are newest-first. Each item embeds title + year projections
    for both sides so the admin UI does not need an extra round-trip
    to render the queue row.
    """
    output = await use_case.execute(
        ListConflictsInput(state=state, source=source, cursor=cursor, limit=limit),
    )
    return api_list(
        [asdict(item) for item in output.items],
        pagination=Pagination(
            has_more=output.has_more,
            next_cursor=output.next_cursor,
        ),
    )


@router.post("/{conflict_id}/resolve")
@inject
async def resolve_admin_conflict(
    body: ResolveConflictBody,
    conflict_id: str = Path(..., min_length=1, max_length=50),
    _admin: UserModel = Depends(current_admin_user),
    use_case: ResolveMediaConflictUseCase = Depends(
        Provide[ApplicationContainer.media.resolve_media_conflict],
    ),
) -> dict[str, Any]:
    """Apply the operator's resolution to a pending conflict.

    - ``mark_distinct``: the pair is intentionally distinct
      (Director's Cut / Theatrical, etc.); the detector will not
      re-queue it on future enrichment passes.
    - ``merge_replace``: soft-deletes the loser movie. Cross-BC
      handlers drop the loser's watch progress and repoint
      watchlist / custom-list entries to the winner.
    - ``merge_keep_both``: same as ``merge_replace`` plus the loser's
      file variants are transferred to the winner so the operator
      can pick the best stream at playback time across what used to
      be two catalog entries.
    """
    output = await use_case.execute(
        ResolveMediaConflictInput(
            conflict_id=conflict_id,
            action=body.action.value,
            winner_id=body.winner_id,
        ),
    )
    return api_single("media_conflict_resolution", asdict(output))


__all__ = ["router"]
