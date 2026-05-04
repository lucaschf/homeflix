"""Pydantic schemas for profile request/response validation."""

from pydantic import BaseModel, Field


class CreateProfileRequest(BaseModel):
    """``POST /api/v1/profiles`` body."""

    name: str = Field(min_length=1, max_length=50)
    is_kids: bool = False
    avatar_url: str | None = Field(default=None, max_length=500)


class UpdateProfileRequest(BaseModel):
    """``PUT /api/v1/profiles/{id}`` body — partial update.

    All fields optional: only supplied fields are mutated. ``None``
    is treated as "field omitted", not "clear the value", to keep
    PATCH-style semantics inside a PUT route.
    """

    name: str | None = Field(default=None, min_length=1, max_length=50)
    is_kids: bool | None = None
    avatar_url: str | None = Field(default=None, max_length=500)


__all__ = ["CreateProfileRequest", "UpdateProfileRequest"]
