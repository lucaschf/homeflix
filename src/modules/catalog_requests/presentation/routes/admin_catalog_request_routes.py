"""Admin REST API routes for the catalog-request queue."""

from dataclasses import asdict
from typing import Any

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends

from src.building_blocks.presentation import api_list
from src.config.containers import ApplicationContainer
from src.modules.catalog_requests.application.dtos import DismissCatalogRequestInput
from src.modules.catalog_requests.application.use_cases import (
    DismissCatalogRequestUseCase,
    ListCatalogRequestsUseCase,
)
from src.modules.catalog_requests.application.use_cases.list_catalog_requests import (
    ListCatalogRequestsInput,
)
from src.modules.identity.infrastructure.auth import current_admin_user
from src.modules.identity.infrastructure.persistence.models.user_model import UserModel

router = APIRouter(prefix="/api/v1/admin", tags=["Admin — Catalog Requests"])


@router.get("/catalog-requests")  # type: ignore[misc]
@inject  # type: ignore[misc]
async def list_admin_catalog_requests(
    _admin: UserModel = Depends(current_admin_user),
    use_case: ListCatalogRequestsUseCase = Depends(
        Provide[ApplicationContainer.catalog_requests.list_catalog_requests],
    ),
) -> dict[str, Any]:
    """List every pending catalog request across the household.

    Same shape as the user-facing ``GET /api/v1/catalog-requests``
    but admin-only; the admin endpoint exists so the panel page can
    sit behind ``RequireAdmin`` even though the user-facing endpoint
    is intentionally available to any authenticated profile.
    """
    items = await use_case.execute(ListCatalogRequestsInput())
    return api_list([asdict(item) for item in items])


@router.delete("/catalog-requests/{request_id}", status_code=204)  # type: ignore[misc]
@inject  # type: ignore[misc]
async def dismiss_catalog_request(
    request_id: str,
    _admin: UserModel = Depends(current_admin_user),
    use_case: DismissCatalogRequestUseCase = Depends(
        Provide[ApplicationContainer.catalog_requests.dismiss_catalog_request],
    ),
) -> None:
    """Soft-delete a catalog request the household no longer wants tracked."""
    await use_case.execute(DismissCatalogRequestInput(request_id=request_id))


__all__ = ["router"]
