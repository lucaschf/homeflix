"""Admin REST API routes for the catalog-request queue."""

from dataclasses import asdict
from typing import Any

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends

from src.building_blocks.presentation import api_list, api_single
from src.config.containers import ApplicationContainer
from src.modules.catalog_requests.application.dtos import (
    DismissCatalogRequestInput,
    IncludeCatalogRequestInput,
)
from src.modules.catalog_requests.application.use_cases import (
    DismissCatalogRequestUseCase,
    IncludeCatalogRequestUseCase,
    ListAdminCatalogRequestsUseCase,
)
from src.modules.identity.infrastructure.auth import current_admin_user
from src.modules.identity.infrastructure.persistence.models.user_model import UserModel

router = APIRouter(prefix="/api/v1/admin", tags=["Admin — Catalog Requests"])


@router.get("/catalog-requests")  # type: ignore[misc]
@inject  # type: ignore[misc]
async def list_admin_catalog_requests(
    lang: str = "en",
    _admin: UserModel = Depends(current_admin_user),
    use_case: ListAdminCatalogRequestsUseCase = Depends(
        Provide[ApplicationContainer.catalog_requests.list_admin_catalog_requests],
    ),
) -> dict[str, Any]:
    """List every pending catalog request with its subscriber count.

    Admin-only queue: each row carries the base request fields
    (including ``source`` + derived ``status``) plus ``subscriber_count``
    (the "Inscritos" column). Admin-gated via ``current_admin_user``.
    ``lang`` selects the per-request localized title snapshot.
    """
    items = await use_case.execute(lang)
    return api_list(
        [{**asdict(item.request), "subscriber_count": item.subscriber_count} for item in items],
    )


@router.post("/catalog-requests/{request_id}/include", status_code=200)  # type: ignore[misc]
@inject  # type: ignore[misc]
async def include_catalog_request(
    request_id: str,
    _admin: UserModel = Depends(current_admin_user),
    use_case: IncludeCatalogRequestUseCase = Depends(
        Provide[ApplicationContainer.catalog_requests.include_catalog_request],
    ),
) -> dict[str, Any]:
    """Mark a request as included — fulfill it and notify every subscriber.

    The manual counterpart to auto-fulfillment, for the orphan-rescue
    case (the title is in the catalog but the request never
    auto-matched). The request leaves the pending queue and each
    subscriber gets the "já disponível" ping. ``404`` when no active
    request matches; idempotent on an already-fulfilled request.
    """
    result = await use_case.execute(IncludeCatalogRequestInput(request_id=request_id))
    return api_single("catalog_request", asdict(result))


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
