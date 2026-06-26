"""Custom List REST API routes."""

from dataclasses import asdict
from typing import Any

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends

from src.building_blocks.presentation import api_list, api_single
from src.config.containers import ApplicationContainer
from src.modules.collections.application.dtos import (
    AddItemToCustomListInput,
    CreateCustomListInput,
    DeleteCustomListInput,
    GetCustomListItemsInput,
    RemoveItemFromCustomListInput,
    RenameCustomListInput,
    ReorderCustomListItemsInput,
)
from src.modules.collections.application.use_cases import (
    AddItemToCustomListUseCase,
    CreateCustomListUseCase,
    DeleteCustomListUseCase,
    GetCustomListItemsUseCase,
    ListCustomListsUseCase,
    RemoveItemFromCustomListUseCase,
    RenameCustomListUseCase,
    ReorderCustomListItemsUseCase,
)
from src.modules.collections.application.use_cases.list_custom_lists import (
    ListCustomListsInput,
)
from src.modules.collections.presentation.dependencies import resolve_profile_id
from src.modules.collections.presentation.schemas import (
    AddItemToCustomListRequest,
    CreateCustomListRequest,
    RenameCustomListRequest,
    ReorderCustomListItemsRequest,
)

router = APIRouter(prefix="/api/v1/custom-lists", tags=["Custom Lists"])


# -- List CRUD -----------------------------------------------------------------


@router.post("")  # type: ignore[misc]
@inject  # type: ignore[misc]
async def create_custom_list(
    body: CreateCustomListRequest,
    profile_id: str = Depends(resolve_profile_id),
    use_case: CreateCustomListUseCase = Depends(
        Provide[ApplicationContainer.collections.create_custom_list],
    ),
) -> dict[str, Any]:
    """Create a new custom list."""
    result = await use_case.execute(
        CreateCustomListInput(profile_id=profile_id, name=body.name, description=body.description)
    )
    return api_single("custom_list", asdict(result))


@router.get("")  # type: ignore[misc]
@inject  # type: ignore[misc]
async def list_custom_lists(
    profile_id: str = Depends(resolve_profile_id),
    use_case: ListCustomListsUseCase = Depends(
        Provide[ApplicationContainer.collections.list_custom_lists],
    ),
) -> dict[str, Any]:
    """List custom lists owned by the caller's profile."""
    items = await use_case.execute(ListCustomListsInput(profile_id=profile_id))
    return api_list([asdict(item) for item in items])


@router.patch("/{list_id}")  # type: ignore[misc]
@inject  # type: ignore[misc]
async def rename_custom_list(
    list_id: str,
    body: RenameCustomListRequest,
    profile_id: str = Depends(resolve_profile_id),
    use_case: RenameCustomListUseCase = Depends(
        Provide[ApplicationContainer.collections.rename_custom_list],
    ),
) -> dict[str, Any]:
    """Rename a custom list owned by the caller."""
    result = await use_case.execute(
        RenameCustomListInput(
            profile_id=profile_id,
            list_id=list_id,
            name=body.name,
            description=body.description,
        )
    )
    return api_single("custom_list", asdict(result))


@router.delete("/{list_id}", status_code=204)  # type: ignore[misc]
@inject  # type: ignore[misc]
async def delete_custom_list(
    list_id: str,
    profile_id: str = Depends(resolve_profile_id),
    use_case: DeleteCustomListUseCase = Depends(
        Provide[ApplicationContainer.collections.delete_custom_list],
    ),
) -> None:
    """Delete a custom list and all its items, scoped to the profile."""
    await use_case.execute(DeleteCustomListInput(profile_id=profile_id, list_id=list_id))


# -- Item management -----------------------------------------------------------


@router.get("/{list_id}/items")  # type: ignore[misc]
@inject  # type: ignore[misc]
async def get_custom_list_items(
    list_id: str,
    lang: str = "en",
    profile_id: str = Depends(resolve_profile_id),
    use_case: GetCustomListItemsUseCase = Depends(
        Provide[ApplicationContainer.collections.get_custom_list_items],
    ),
) -> dict[str, Any]:
    """List items in a custom list with media metadata."""
    items = await use_case.execute(
        GetCustomListItemsInput(profile_id=profile_id, list_id=list_id, lang=lang)
    )
    return api_list([asdict(item) for item in items])


@router.post("/{list_id}/items", status_code=201)  # type: ignore[misc]
@inject  # type: ignore[misc]
async def add_item_to_custom_list(
    list_id: str,
    body: AddItemToCustomListRequest,
    profile_id: str = Depends(resolve_profile_id),
    use_case: AddItemToCustomListUseCase = Depends(
        Provide[ApplicationContainer.collections.add_item_to_custom_list],
    ),
) -> dict[str, Any]:
    """Add a media item to a custom list owned by the caller."""
    await use_case.execute(
        AddItemToCustomListInput(
            profile_id=profile_id,
            list_id=list_id,
            media_id=body.media_id,
            media_type=body.media_type,
        ),
    )
    return api_single(
        "custom_list",
        {"list_id": list_id, "media_id": body.media_id, "added": True},
    )


@router.patch("/{list_id}/items/order", status_code=204)  # type: ignore[misc]
@inject  # type: ignore[misc]
async def reorder_custom_list_items(
    list_id: str,
    body: ReorderCustomListItemsRequest,
    profile_id: str = Depends(resolve_profile_id),
    use_case: ReorderCustomListItemsUseCase = Depends(
        Provide[ApplicationContainer.collections.reorder_custom_list_items],
    ),
) -> None:
    """Persist a manual item order for a custom list owned by the caller."""
    await use_case.execute(
        ReorderCustomListItemsInput(
            profile_id=profile_id,
            list_id=list_id,
            media_ids=tuple(body.media_ids),
        )
    )


@router.delete("/{list_id}/items/{media_id}", status_code=204)  # type: ignore[misc]
@inject  # type: ignore[misc]
async def remove_item_from_custom_list(
    list_id: str,
    media_id: str,
    profile_id: str = Depends(resolve_profile_id),
    use_case: RemoveItemFromCustomListUseCase = Depends(
        Provide[ApplicationContainer.collections.remove_item_from_custom_list],
    ),
) -> None:
    """Remove a media item from a custom list owned by the caller."""
    await use_case.execute(
        RemoveItemFromCustomListInput(profile_id=profile_id, list_id=list_id, media_id=media_id)
    )


__all__ = ["router"]
