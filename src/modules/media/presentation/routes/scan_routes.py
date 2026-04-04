"""Media scan REST API routes."""

from dataclasses import asdict
from typing import Any

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends

from src.config.containers import ApplicationContainer
from src.modules.media.application.dtos.scan_dtos import ScanMediaInput
from src.modules.media.application.use_cases.scan_media_directories import (
    ScanMediaDirectoriesUseCase,
)
from src.modules.media.presentation.schemas import ScanMediaRequest, ScanMediaResponse
from src.shared_kernel.value_objects.file_path import FilePath

router = APIRouter(prefix="/api/v1/scan", tags=["Scan"])


@router.post("", response_model=ScanMediaResponse)  # type: ignore[misc]
@inject  # type: ignore[misc]
async def scan_media(
    body: ScanMediaRequest | None = None,
    use_case: ScanMediaDirectoriesUseCase = Depends(
        Provide[ApplicationContainer.media.scan_media_directories],
    ),
) -> dict[str, Any]:
    """Trigger a media directory scan.

    Scans configured directories (or overrides from request body)
    for movie and episode files, registering them in the database.
    """
    directories = [FilePath(d) for d in body.directories] if body and body.directories else []
    input_dto = ScanMediaInput(directories=directories)
    output = await use_case.execute(input_dto)
    return asdict(output)


__all__ = ["router"]
