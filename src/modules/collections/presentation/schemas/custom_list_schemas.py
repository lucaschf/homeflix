"""Custom list request/response schemas."""

from pydantic import BaseModel, Field

from src.shared_kernel.value_objects import MediaType


class CreateCustomListRequest(BaseModel):
    """Request body for creating a custom list."""

    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=500)


class RenameCustomListRequest(BaseModel):
    """Request body for editing a custom list (name + description)."""

    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=500)


class AddItemToCustomListRequest(BaseModel):
    """Request body for adding an item to a custom list."""

    media_id: str
    media_type: MediaType


class ReorderCustomListItemsRequest(BaseModel):
    """Request body for reordering a custom list's items.

    ``media_ids`` is the full set of the list's item ids in the desired
    order; each item's position becomes its index.
    """

    media_ids: list[str] = Field(..., min_length=1)


__all__ = [
    "AddItemToCustomListRequest",
    "CreateCustomListRequest",
    "RenameCustomListRequest",
    "ReorderCustomListItemsRequest",
]
