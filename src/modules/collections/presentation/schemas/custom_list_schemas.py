"""Custom list request/response schemas."""

from pydantic import BaseModel, Field

from src.shared_kernel.value_objects import CollectionMediaType


class CreateCustomListRequest(BaseModel):
    """Request body for creating a custom list."""

    name: str = Field(..., min_length=1, max_length=200)


class RenameCustomListRequest(BaseModel):
    """Request body for renaming a custom list."""

    name: str = Field(..., min_length=1, max_length=200)


class AddItemToCustomListRequest(BaseModel):
    """Request body for adding an item to a custom list."""

    media_id: str
    media_type: CollectionMediaType


__all__ = [
    "AddItemToCustomListRequest",
    "CreateCustomListRequest",
    "RenameCustomListRequest",
]
