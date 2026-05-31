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
    BulkMarkDistinctInput,
    ListConflictsInput,
    ResolveMediaConflictInput,
)
from src.modules.media.application.use_cases.bulk_mark_distinct_conflicts import (
    BulkMarkDistinctConflictsUseCase,
)
from src.modules.media.application.use_cases.list_conflicts import ListConflictsUseCase
from src.modules.media.application.use_cases.resolve_media_conflict import (
    ResolveMediaConflictUseCase,
)
from src.modules.media.application.use_cases.sweep_movie_conflicts import (
    SweepMovieConflictsUseCase,
)
from src.modules.media.domain.entities.media_conflict import ResolutionAction

_MAX_BULK_CONFLICTS = 200


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


class BulkMarkDistinctBody(BaseModel):
    """Request body for ``POST /admin/conflicts/bulk-mark-distinct``.

    ``conflict_ids`` is bounded so a single call can't sweep an
    unbounded queue; the use case de-duplicates and skips ids that
    are missing, malformed, or already resolved.
    """

    conflict_ids: list[str] = Field(
        ...,
        min_length=1,
        max_length=_MAX_BULK_CONFLICTS,
        description="External ids (cnf_xxx) of pending conflicts to mark distinct.",
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


@router.post("/bulk-mark-distinct")
@inject
async def bulk_mark_distinct_conflicts(
    body: BulkMarkDistinctBody,
    _admin: UserModel = Depends(current_admin_user),
    use_case: BulkMarkDistinctConflictsUseCase = Depends(
        Provide[ApplicationContainer.media.bulk_mark_distinct_conflicts],
    ),
) -> dict[str, Any]:
    """Mark a selection of pending conflicts as intentionally distinct.

    Bulk resolution only supports ``mark_distinct`` — it needs no
    per-conflict winner and triggers no soft-delete, so a whole
    selection closes safely in one transaction. Ids that are missing,
    malformed, or already resolved are reported under ``skipped``
    instead of failing the request.
    """
    output = await use_case.execute(
        BulkMarkDistinctInput(conflict_ids=body.conflict_ids),
    )
    return api_single("media_conflict_bulk_resolution", asdict(output))


@router.post("/sweep")
@inject
async def sweep_admin_conflicts(
    _admin: UserModel = Depends(current_admin_user),
    use_case: SweepMovieConflictsUseCase = Depends(
        Provide[ApplicationContainer.media.sweep_movie_conflicts],
    ),
) -> dict[str, Any]:
    """Trigger a one-off catalog-wide dedup sweep (ADR-015 Phase 6.5).

    Re-runs the conflict detector against every movie in the catalog,
    no enrichment required. Use it to catch duplicates the event-driven
    handler missed — e.g. a second copy that landed *after* the first
    was already enriched, or a pair where neither side ever locked a
    TMDB id (handled by the title+year fallback).

    The same pass also runs automatically when the scheduled sweep is
    enabled in the ``scan_dedup`` settings bucket. The manual endpoint
    ignores that flag so the operator can re-check on demand even when
    the recurring job is off.
    """
    output = await use_case.execute()
    return api_single("media_conflict_sweep", asdict(output))


__all__ = ["router"]
