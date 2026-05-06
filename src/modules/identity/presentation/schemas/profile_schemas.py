"""Pydantic schemas for profile request/response validation."""

from pydantic import BaseModel, Field


class CreateProfileRequest(BaseModel):
    """``POST /api/v1/profiles`` body.

    ``allowed_library_ids`` is omitted by default — the new profile
    starts with no library access (the ACL is default-deny). The
    admin / profile owner grants access via this field at creation
    time, or later via ``PUT /api/v1/profiles/{id}``.
    """

    name: str = Field(min_length=1, max_length=50)
    is_kids: bool = False
    avatar_url: str | None = Field(default=None, max_length=500)
    allowed_library_ids: list[str] | None = Field(default=None)


class UpdateProfileRequest(BaseModel):
    """``PUT /api/v1/profiles/{id}`` body — partial update.

    All fields optional: only supplied fields are mutated. ``None``
    is treated as "field omitted", not "clear the value", to keep
    PATCH-style semantics inside a PUT route. To revoke every
    library, send ``allowed_library_ids: []`` explicitly — the empty
    list is meaningful, ``null`` is not.
    """

    name: str | None = Field(default=None, min_length=1, max_length=50)
    is_kids: bool | None = None
    avatar_url: str | None = Field(default=None, max_length=500)
    allowed_library_ids: list[str] | None = Field(default=None)


__all__ = ["CreateProfileRequest", "UpdateProfileRequest"]
