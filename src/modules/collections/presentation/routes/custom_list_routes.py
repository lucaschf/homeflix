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
    FollowSharedListInput,
    GetCustomListItemsInput,
    GetSharedListPreviewInput,
    RemoveItemFromCustomListInput,
    RenameCustomListInput,
    ReorderCustomListItemsInput,
    RevokeCustomListShareInput,
    ShareCustomListInput,
    UnfollowCustomListInput,
)
from src.modules.collections.application.use_cases import (
    AddItemToCustomListUseCase,
    CreateCustomListUseCase,
    DeleteCustomListUseCase,
    FollowSharedListUseCase,
    GetCustomListItemsUseCase,
    GetSharedListPreviewUseCase,
    ListCustomListsUseCase,
    RemoveItemFromCustomListUseCase,
    RenameCustomListUseCase,
    ReorderCustomListItemsUseCase,
    RevokeCustomListShareUseCase,
    ShareCustomListUseCase,
    UnfollowCustomListUseCase,
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


@router.post("")
@inject
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


@router.get("")
@inject
async def list_custom_lists(
    profile_id: str = Depends(resolve_profile_id),
    use_case: ListCustomListsUseCase = Depends(
        Provide[ApplicationContainer.collections.list_custom_lists],
    ),
) -> dict[str, Any]:
    """List custom lists owned by the caller's profile."""
    items = await use_case.execute(ListCustomListsInput(profile_id=profile_id))
    return api_list([asdict(item) for item in items])


@router.patch("/{list_id}")
@inject
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


@router.delete("/{list_id}", status_code=204)
@inject
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


@router.get("/{list_id}/items")
@inject
async def get_custom_list_items(
    list_id: str,
    lang: str = "en",
    profile_id: str = Depends(resolve_profile_id),
    use_case: GetCustomListItemsUseCase = Depends(
        Provide[ApplicationContainer.collections.get_custom_list_items],
    ),
) -> dict[str, Any]:
    """List items in a custom list with media metadata.

    Serves the owner's own list *and* a list the caller follows. On a
    followed list, items the caller's profile can't access are filtered
    out and reported via ``metadata.hidden_count``.
    """
    result = await use_case.execute(
        GetCustomListItemsInput(profile_id=profile_id, list_id=list_id, lang=lang)
    )
    return api_list(
        [asdict(item) for item in result.items],
        metadata_extras={"hidden_count": result.hidden_count},
    )


@router.post("/{list_id}/items", status_code=201)
@inject
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


@router.patch("/{list_id}/items/order", status_code=204)
@inject
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


@router.delete("/{list_id}/items/{media_id}", status_code=204)
@inject
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


# -- Sharing & following -------------------------------------------------------


@router.post("/{list_id}/share")
@inject
async def share_custom_list(
    list_id: str,
    profile_id: str = Depends(resolve_profile_id),
    use_case: ShareCustomListUseCase = Depends(
        Provide[ApplicationContainer.collections.share_custom_list],
    ),
) -> dict[str, Any]:
    """Mint (or return the existing) share token for a list the caller owns."""
    result = await use_case.execute(ShareCustomListInput(profile_id=profile_id, list_id=list_id))
    return api_single("custom_list_share", asdict(result))


@router.delete("/{list_id}/share", status_code=204)
@inject
async def revoke_custom_list_share(
    list_id: str,
    profile_id: str = Depends(resolve_profile_id),
    use_case: RevokeCustomListShareUseCase = Depends(
        Provide[ApplicationContainer.collections.revoke_custom_list_share],
    ),
) -> None:
    """Stop sharing a list: invalidate the token and drop its followers."""
    await use_case.execute(RevokeCustomListShareInput(profile_id=profile_id, list_id=list_id))


@router.get("/shared/{token}")
@inject
async def get_shared_list_preview(
    token: str,
    lang: str = "en",
    profile_id: str = Depends(resolve_profile_id),
    use_case: GetSharedListPreviewUseCase = Depends(
        Provide[ApplicationContainer.collections.get_shared_list_preview],
    ),
) -> dict[str, Any]:
    """Read-only preview of a shared list, filtered by the caller's access."""
    result = await use_case.execute(
        GetSharedListPreviewInput(profile_id=profile_id, token=token, lang=lang)
    )
    return api_single("shared_list", asdict(result))


@router.post("/shared/{token}/follow", status_code=204)
@inject
async def follow_shared_list(
    token: str,
    profile_id: str = Depends(resolve_profile_id),
    use_case: FollowSharedListUseCase = Depends(
        Provide[ApplicationContainer.collections.follow_shared_list],
    ),
) -> None:
    """Follow a shared list by token (idempotent)."""
    await use_case.execute(FollowSharedListInput(profile_id=profile_id, token=token))


@router.delete("/{list_id}/follow", status_code=204)
@inject
async def unfollow_custom_list(
    list_id: str,
    profile_id: str = Depends(resolve_profile_id),
    use_case: UnfollowCustomListUseCase = Depends(
        Provide[ApplicationContainer.collections.unfollow_custom_list],
    ),
) -> None:
    """Stop following a list (idempotent)."""
    await use_case.execute(UnfollowCustomListInput(profile_id=profile_id, list_id=list_id))


__all__ = ["router"]
