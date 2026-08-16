"""Media scan REST API routes."""

from dataclasses import asdict
from typing import Any

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, HTTPException, status

from src.building_blocks.presentation import api_single
from src.config.containers import ApplicationContainer
from src.modules.identity.infrastructure.auth import AuthenticatedUser, authenticated_admin
from src.modules.media.application.dtos.scan_dtos import ScanMediaInput
from src.modules.media.application.ports.library_lookup_port import LibraryLookupPort
from src.modules.media.application.use_cases.scan_media_directories import (
    ScanMediaDirectoriesUseCase,
)
from src.modules.media.presentation.schemas import ScanMediaRequest

router = APIRouter(prefix="/api/v1/scan", tags=["Scan"])


@router.post("")
@inject
async def scan_media(
    body: ScanMediaRequest,
    _admin: AuthenticatedUser = Depends(authenticated_admin),
    use_case: ScanMediaDirectoriesUseCase = Depends(
        Provide[ApplicationContainer.media.scan_media_directories],
    ),
    library_lookup: LibraryLookupPort = Depends(
        Provide[ApplicationContainer.media.library_lookup],
    ),
) -> dict[str, Any]:
    """Trigger a scan of the named library's configured paths.

    The route resolves the library's paths through the cross-BC
    ``LibraryLookupPort`` so the operator only has to know the
    ``lib_xxx`` id — paths and the per-Movie / per-Series
    ``library_id`` propagate from a single source of truth.
    """
    library = await library_lookup.find(body.library_id)
    if library is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Library {body.library_id} not found",
        )

    input_dto = ScanMediaInput(
        library_id=library.id,
        directories=list(library.paths),
    )
    output = await use_case.execute(input_dto)
    return api_single("scan", asdict(output))


__all__ = ["router"]
