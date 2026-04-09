"""Custom List REST API routes."""

from dataclasses import asdict
from typing import Any

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends

from src.config.containers import ApplicationContainer
from src.modules.collections.application.dtos import (
    AddItemToCustomListInput,
    CreateCustomListInput,
    GetCustomListItemsInput,
    RemoveItemFromCustomListInput,
    RenameCustomListInput,
)
from src.modules.collections.application.use_cases import (
    AddItemToCustomListUseCase,
    CreateCustomListUseCase,
    DeleteCustomListUseCase,
    GetCustomListItemsUseCase,
    ListCustomListsUseCase,
    RemoveItemFromCustomListUseCase,
    RenameCustomListUseCase,
)
from src.modules.collections.presentation.schemas import (
    AddItemToCustomListRequest,
    CreateCustomListRequest,
    RenameCustomListRequest,
)

router = APIRouter(prefix="/api/v1/custom-lists", tags=["Custom Lists"])


# -- List CRUD -----------------------------------------------------------------


@router.post("")  # type: ignore[misc]
@inject  # type: ignore[misc]
async def create_custom_list(
    body: CreateCustomListRequest,
    use_case: CreateCustomListUseCase = Depends(
        Provide[ApplicationContainer.collections.create_custom_list],
    ),
) -> dict[str, Any]:
    """Create a new custom list."""
    result = await use_case.execute(CreateCustomListInput(name=body.name))
    return {"type": "custom_list", "data": asdict(result)}


@router.get("")  # type: ignore[misc]
@inject  # type: ignore[misc]
async def list_custom_lists(
    use_case: ListCustomListsUseCase = Depends(
        Provide[ApplicationContainer.collections.list_custom_lists],
    ),
) -> dict[str, Any]:
    """List all custom lists."""
    items = await use_case.execute()
    return {"type": "list", "data": [asdict(item) for item in items]}


@router.patch("/{list_id}")  # type: ignore[misc]
@inject  # type: ignore[misc]
async def rename_custom_list(
    list_id: str,
    body: RenameCustomListRequest,
    use_case: RenameCustomListUseCase = Depends(
        Provide[ApplicationContainer.collections.rename_custom_list],
    ),
) -> dict[str, Any]:
    """Rename a custom list."""
    result = await use_case.execute(RenameCustomListInput(list_id=list_id, name=body.name))
    return {"type": "custom_list", "data": asdict(result)}


@router.delete("/{list_id}", status_code=204)  # type: ignore[misc]
@inject  # type: ignore[misc]
async def delete_custom_list(
    list_id: str,
    use_case: DeleteCustomListUseCase = Depends(
        Provide[ApplicationContainer.collections.delete_custom_list],
    ),
) -> None:
    """Delete a custom list and all its items."""
    await use_case.execute(list_id)


# -- Item management -----------------------------------------------------------


@router.get("/{list_id}/items")  # type: ignore[misc]
@inject  # type: ignore[misc]
async def get_custom_list_items(
    list_id: str,
    lang: str = "en",
    use_case: GetCustomListItemsUseCase = Depends(
        Provide[ApplicationContainer.collections.get_custom_list_items],
    ),
) -> dict[str, Any]:
    """List all items in a custom list with media metadata."""
    items = await use_case.execute(GetCustomListItemsInput(list_id=list_id, lang=lang))
    return {"type": "list", "data": [asdict(item) for item in items]}


@router.post("/{list_id}/items", status_code=201)  # type: ignore[misc]
@inject  # type: ignore[misc]
async def add_item_to_custom_list(
    list_id: str,
    body: AddItemToCustomListRequest,
    use_case: AddItemToCustomListUseCase = Depends(
        Provide[ApplicationContainer.collections.add_item_to_custom_list],
    ),
) -> dict[str, Any]:
    """Add a media item to a custom list."""
    await use_case.execute(
        AddItemToCustomListInput(
            list_id=list_id,
            media_id=body.media_id,
            media_type=body.media_type,
        ),
    )
    return {
        "type": "custom_list",
        "data": {"list_id": list_id, "media_id": body.media_id, "added": True},
    }


@router.delete("/{list_id}/items/{media_id}", status_code=204)  # type: ignore[misc]
@inject  # type: ignore[misc]
async def remove_item_from_custom_list(
    list_id: str,
    media_id: str,
    use_case: RemoveItemFromCustomListUseCase = Depends(
        Provide[ApplicationContainer.collections.remove_item_from_custom_list],
    ),
) -> None:
    """Remove a media item from a custom list."""
    await use_case.execute(RemoveItemFromCustomListInput(list_id=list_id, media_id=media_id))


__all__ = ["router"]
