"""Media scan REST API routes."""

from dataclasses import asdict
from typing import Any

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, HTTPException, status

from src.building_blocks.presentation import api_single
from src.config.containers import ApplicationContainer
from src.modules.identity.infrastructure.auth import current_admin_user
from src.modules.identity.infrastructure.persistence.models.user_model import UserModel
from src.modules.library.application.unit_of_work import LibraryUnitOfWorkFactory
from src.modules.media.application.dtos.scan_dtos import ScanMediaInput
from src.modules.media.application.use_cases.scan_media_directories import (
    ScanMediaDirectoriesUseCase,
)
from src.modules.media.presentation.schemas import ScanMediaRequest
from src.shared_kernel.value_objects.library_id import LibraryId

router = APIRouter(prefix="/api/v1/scan", tags=["Scan"])


@router.post("")  # type: ignore[misc]
@inject  # type: ignore[misc]
async def scan_media(
    body: ScanMediaRequest,
    _admin: UserModel = Depends(current_admin_user),
    use_case: ScanMediaDirectoriesUseCase = Depends(
        Provide[ApplicationContainer.media.scan_media_directories],
    ),
    library_uow_factory: LibraryUnitOfWorkFactory = Depends(
        Provide[ApplicationContainer.library.library_unit_of_work_factory],
    ),
) -> dict[str, Any]:
    """Trigger a scan of the named library's configured paths.

    The route loads the library to get its paths so the operator
    only has to know the ``lib_xxx`` id — paths and the per-Movie /
    per-Series ``library_id`` propagate from a single source of truth.
    """
    async with library_uow_factory() as uow:
        library = await uow.libraries.find_by_id(LibraryId(body.library_id))
    if library is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Library {body.library_id} not found",
        )

    input_dto = ScanMediaInput(
        library_id=str(library.id),
        directories=list(library.paths),
    )
    output = await use_case.execute(input_dto)
    return api_single("scan", asdict(output))


__all__ = ["router"]
