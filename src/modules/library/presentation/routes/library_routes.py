"""Library CRUD REST API routes."""

from dataclasses import asdict
from typing import Any

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends

from src.building_blocks.presentation import api_list, api_single
from src.config.containers import ApplicationContainer
from src.modules.identity.infrastructure.auth import AuthenticatedUser, authenticated_admin
from src.modules.library.application.dtos.library_dtos import (
    CreateLibraryInput,
    DeleteLibraryInput,
    GetLibraryByIdInput,
    UpdateLibraryInput,
)
from src.modules.library.application.use_cases.create_library import CreateLibraryUseCase
from src.modules.library.application.use_cases.delete_library import DeleteLibraryUseCase
from src.modules.library.application.use_cases.get_library_by_id import GetLibraryByIdUseCase
from src.modules.library.application.use_cases.list_libraries import ListLibrariesUseCase
from src.modules.library.application.use_cases.update_library import UpdateLibraryUseCase
from src.modules.library.presentation.schemas.library_schemas import (
    CreateLibraryRequest,
    UpdateLibraryRequest,
)

router = APIRouter(prefix="/api/v1/libraries", tags=["Libraries"])


@router.post("")
@inject
async def create_library(
    body: CreateLibraryRequest,
    _admin: AuthenticatedUser = Depends(authenticated_admin),
    use_case: CreateLibraryUseCase = Depends(
        Provide[ApplicationContainer.library.create_library],
    ),
) -> dict[str, Any]:
    """Create a new media library."""
    result = await use_case.execute(
        CreateLibraryInput(
            name=body.name,
            library_type=body.library_type,
            paths=body.paths,
            language=body.language,
            metadata_providers=[p.to_config() for p in body.metadata_providers],
            scan_schedule=body.scan_schedule,
            settings=body.settings.to_settings() if body.settings else None,
        )
    )
    return api_single("library", asdict(result))


@router.get("")
@inject
async def list_libraries(
    use_case: ListLibrariesUseCase = Depends(
        Provide[ApplicationContainer.library.list_libraries],
    ),
) -> dict[str, Any]:
    """List all non-deleted libraries."""
    result = await use_case.execute()
    return api_list([asdict(lib) for lib in result])


@router.get("/{library_id}")
@inject
async def get_library(
    library_id: str,
    use_case: GetLibraryByIdUseCase = Depends(
        Provide[ApplicationContainer.library.get_library_by_id],
    ),
) -> dict[str, Any]:
    """Get a library by its external id."""
    result = await use_case.execute(GetLibraryByIdInput(library_id=library_id))
    return api_single("library", asdict(result))


@router.put("/{library_id}")
@inject
async def update_library(
    library_id: str,
    body: UpdateLibraryRequest,
    _admin: AuthenticatedUser = Depends(authenticated_admin),
    use_case: UpdateLibraryUseCase = Depends(
        Provide[ApplicationContainer.library.update_library],
    ),
) -> dict[str, Any]:
    """Partially update a library."""
    result = await use_case.execute(
        UpdateLibraryInput(
            library_id=library_id,
            name=body.name,
            library_type=body.library_type,
            paths=body.paths,
            language=body.language,
            metadata_providers=(
                [p.to_config() for p in body.metadata_providers]
                if body.metadata_providers is not None
                else None
            ),
            scan_schedule=body.scan_schedule,
            settings=body.settings.to_settings() if body.settings else None,
        )
    )
    return api_single("library", asdict(result))


@router.delete("/{library_id}", status_code=204)
@inject
async def delete_library(
    library_id: str,
    _admin: AuthenticatedUser = Depends(authenticated_admin),
    use_case: DeleteLibraryUseCase = Depends(
        Provide[ApplicationContainer.library.delete_library],
    ),
) -> None:
    """Soft-delete a library."""
    await use_case.execute(DeleteLibraryInput(library_id=library_id))


__all__ = ["router"]
