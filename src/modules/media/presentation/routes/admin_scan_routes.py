"""Admin REST API routes for scan + bulk-enrich history."""

from dataclasses import asdict
from typing import Any

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from src.building_blocks.presentation import api_list, api_single
from src.config.containers import ApplicationContainer
from src.modules.identity.presentation.public import AuthenticatedUser, authenticated_admin
from src.modules.media.application.dtos.scan_run_dtos import (
    GetScanRunInput,
    ListScanRunsInput,
    TriggerBulkEnrichInput,
    TriggerScanInput,
)
from src.modules.media.application.use_cases.get_scan_run import GetScanRunUseCase
from src.modules.media.application.use_cases.list_scan_runs import ListScanRunsUseCase
from src.modules.media.application.use_cases.trigger_bulk_enrich import (
    TriggerBulkEnrichUseCase,
)
from src.modules.media.application.use_cases.trigger_scan import (
    LibraryNotFoundForScanError,
    TriggerScanUseCase,
)

router = APIRouter(prefix="/api/v1/admin", tags=["Admin — Scan & Enrich"])


class TriggerScanRequest(BaseModel):
    """Body for ``POST /api/v1/admin/scans``."""

    library_id: str


class TriggerBulkEnrichRequest(BaseModel):
    """Body for ``POST /api/v1/admin/enrichments``."""

    force: bool = False


@router.get("/scans")
@inject
async def list_admin_scans(
    kind: str | None = None,
    trigger: str | None = None,
    library_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
    _admin: AuthenticatedUser = Depends(authenticated_admin),
    use_case: ListScanRunsUseCase = Depends(
        Provide[ApplicationContainer.media.list_scan_runs],
    ),
) -> dict[str, Any]:
    """List scan + bulk-enrich runs, newest-first.

    Filters are all optional; ``kind=scan`` returns only catalog
    scans, ``trigger=scheduled`` only background-poller rows. The
    admin Scan and Enrich pages each prefill a different ``kind``
    filter but otherwise share the same backing endpoint.
    """
    rows = await use_case.execute(
        ListScanRunsInput(
            kind=kind,
            trigger=trigger,
            library_id=library_id,
            limit=limit,
            offset=offset,
        ),
    )
    return api_list([asdict(r) for r in rows])


@router.get("/scans/{run_id}")
@inject
async def get_admin_scan(
    run_id: str,
    _admin: AuthenticatedUser = Depends(authenticated_admin),
    use_case: GetScanRunUseCase = Depends(
        Provide[ApplicationContainer.media.get_scan_run],
    ),
) -> dict[str, Any]:
    """Fetch a single run; used by the page-poll loop while ``status=running``."""
    output = await use_case.execute(GetScanRunInput(run_id=run_id))
    return api_single("scan_run", asdict(output))


@router.post("/scans", status_code=202)
@inject
async def trigger_admin_scan(
    body: TriggerScanRequest,
    _admin: AuthenticatedUser = Depends(authenticated_admin),
    use_case: TriggerScanUseCase = Depends(
        Provide[ApplicationContainer.media.trigger_scan],
    ),
) -> dict[str, Any]:
    """Open a ``running`` row + dispatch the scan to a background task.

    Returns 202 with the newly-created run shape so the admin page
    can route to its detail view and start polling immediately.
    The actual ffprobe + DB writes run after the response is sent.
    """
    try:
        output = await use_case.execute(
            TriggerScanInput(library_id=body.library_id, trigger="manual"),
        )
    except LibraryNotFoundForScanError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Library {exc.library_id} not found",
        ) from exc
    return api_single("scan_run", asdict(output))


@router.post("/enrichments", status_code=202)
@inject
async def trigger_admin_bulk_enrich(
    body: TriggerBulkEnrichRequest,
    _admin: AuthenticatedUser = Depends(authenticated_admin),
    use_case: TriggerBulkEnrichUseCase = Depends(
        Provide[ApplicationContainer.media.trigger_bulk_enrich],
    ),
) -> dict[str, Any]:
    """Open an ``enrich`` ``running`` row + dispatch the bulk refresh."""
    output = await use_case.execute(
        TriggerBulkEnrichInput(force=body.force, trigger="manual"),
    )
    return api_single("scan_run", asdict(output))


__all__ = ["router"]
