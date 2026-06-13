"""Catalog Requests REST API routes."""

from dataclasses import asdict
from typing import Any

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from src.building_blocks.presentation import api_list, api_single
from src.config.containers import ApplicationContainer
from src.modules.catalog_requests.application.dtos import (
    CreateCatalogRequestInput,
    SubscribeCatalogNotificationInput,
)
from src.modules.catalog_requests.application.use_cases import (
    ListCatalogRequestsUseCase,
    RequestCatalogInclusionUseCase,
    SubscribeCatalogNotificationUseCase,
)
from src.modules.catalog_requests.application.use_cases.list_catalog_requests import (
    ListCatalogRequestsInput,
)
from src.modules.identity.infrastructure.auth import current_active_user
from src.modules.identity.infrastructure.persistence.models.user_model import UserModel
from src.shared_kernel.value_objects import MediaType

router = APIRouter(prefix="/api/v1/catalog-requests", tags=["Catalog Requests"])


# -- Schemas -------------------------------------------------------------------


class CreateCatalogRequestRequest(BaseModel):
    """Request body for ``POST /catalog-requests``.

    Attributes:
        tmdb_id: TMDB numeric id of the title to request.
        media_type: ``"movie"`` or ``"series"``.
        title: Snapshot of the TMDB title at request time. Optional
            for backwards compatibility with older clients; the
            Collection Detail page sends it in so the admin queue
            can render the title inline without a TMDB round-trip.
        collection_tmdb_id: Optional TMDB collection id that
            surfaced this request — set when the user clicks
            "Solicitar inclusão" from a Collection Detail page.
        notify_on_arrival: Subscribe to the arrival notification
            in the same call. Defaults to ``False`` so the
            "request" and "request + notify" cases stay distinct.
    """

    tmdb_id: int = Field(..., ge=1)
    media_type: MediaType
    title: str | None = Field(default=None, max_length=500)
    collection_tmdb_id: int | None = Field(default=None, ge=1)
    notify_on_arrival: bool = False


class SubscribeNotifyRequest(BaseModel):
    """Request body for the notification-subscribe endpoint."""

    media_type: MediaType
    title: str | None = Field(default=None, max_length=500)
    collection_tmdb_id: int | None = Field(default=None, ge=1)


# -- Endpoints -----------------------------------------------------------------


@router.post("", status_code=201)  # type: ignore[misc]
@inject  # type: ignore[misc]
async def create_catalog_request(
    body: CreateCatalogRequestRequest,
    user: UserModel = Depends(current_active_user),
    use_case: RequestCatalogInclusionUseCase = Depends(
        Provide[ApplicationContainer.catalog_requests.request_catalog_inclusion],
    ),
) -> dict[str, Any]:
    """Register a catalog inclusion request.

    Idempotent on ``(tmdb_id, media_type)``: a repeat call returns
    the existing request unchanged. Passing ``notify_on_arrival=true``
    on a repeat call flips notifications on if they were off. The
    request is tagged with the caller's user id so the arrival
    notification (Layer B) reaches the right inbox; a repeat by a
    different user keeps the original owner (first-owner wins).
    """
    result = await use_case.execute(
        CreateCatalogRequestInput(
            tmdb_id=body.tmdb_id,
            media_type=body.media_type,
            title=body.title,
            requester_user_id=user.external_id,
            collection_tmdb_id=body.collection_tmdb_id,
            notify_on_arrival=body.notify_on_arrival,
        ),
    )
    return api_single("catalog_request", asdict(result))


@router.post("/{tmdb_id}/notify", status_code=200)  # type: ignore[misc]
@inject  # type: ignore[misc]
async def subscribe_catalog_notification(
    tmdb_id: int,
    body: SubscribeNotifyRequest,
    user: UserModel = Depends(current_active_user),
    use_case: SubscribeCatalogNotificationUseCase = Depends(
        Provide[ApplicationContainer.catalog_requests.subscribe_catalog_notification],
    ),
) -> dict[str, Any]:
    """Subscribe to the "title now available" notification.

    Creates a ``CatalogRequest`` if none exists yet, or just flips
    ``notify_on_arrival`` to ``True`` on the existing one. The
    requester user id is backfilled when the existing row was
    created without one (legacy / programmatic seed).
    """
    result = await use_case.execute(
        SubscribeCatalogNotificationInput(
            tmdb_id=tmdb_id,
            media_type=body.media_type,
            title=body.title,
            requester_user_id=user.external_id,
            collection_tmdb_id=body.collection_tmdb_id,
        ),
    )
    return api_single("catalog_request", asdict(result))


@router.get("")  # type: ignore[misc]
@inject  # type: ignore[misc]
async def list_catalog_requests(
    collection_tmdb_id: int | None = Query(default=None, ge=1),
    use_case: ListCatalogRequestsUseCase = Depends(
        Provide[ApplicationContainer.catalog_requests.list_catalog_requests],
    ),
) -> dict[str, Any]:
    """List all pending (unfulfilled) catalog requests."""
    items = await use_case.execute(
        ListCatalogRequestsInput(collection_tmdb_id=collection_tmdb_id),
    )
    return api_list([asdict(item) for item in items])


__all__ = ["router"]
