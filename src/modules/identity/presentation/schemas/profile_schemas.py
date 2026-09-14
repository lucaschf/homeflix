"""Pydantic schemas for profile request/response validation."""

from pydantic import BaseModel, Field, StrictInt


class CreateProfileRequest(BaseModel):
    """``POST /api/v1/profiles`` body.

    ``allowed_library_ids`` is omitted by default — the new profile
    starts with no library access (the ACL is default-deny). The
    admin / profile owner grants access via this field at creation
    time, or later via ``PUT /api/v1/profiles/{id}``.

    ``maturity_limit`` is the highest minimum age the profile may watch,
    0 to 21, or ``null``/omitted for unrestricted (ADR-035). It is a strict
    integer: ``true``, ``"12"`` and ``12.0`` are rejected rather than
    coerced into a limit.

    ``is_kids`` is no longer a field: it is derived from the profile's
    maturity limit (ADR-035). Clients that still send it are not
    rejected — undeclared fields are ignored — but the value is
    discarded.
    """

    name: str = Field(min_length=1, max_length=50)
    avatar_url: str | None = Field(default=None, max_length=500)
    allowed_library_ids: list[str] | None = Field(default=None)
    maturity_limit: StrictInt | None = Field(default=None, ge=0, le=21)


class UpdateProfileRequest(BaseModel):
    """``PUT /api/v1/profiles/{id}`` body — partial update.

    All fields optional: only supplied fields are mutated. ``None``
    is treated as "field omitted", not "clear the value", to keep
    PATCH-style semantics inside a PUT route. To revoke every
    library, send ``allowed_library_ids: []`` explicitly — the empty
    list is meaningful, ``null`` is not.

    ``maturity_limit`` is the exception: ``null`` removes the limit, and
    only an omitted field leaves it alone. The route tells the two apart
    through ``model_fields_set``. It is a strict integer from 0 to 21.

    ``is_kids`` is accepted and ignored, as on create: it is derived
    from the maturity limit (ADR-035).
    """

    name: str | None = Field(default=None, min_length=1, max_length=50)
    avatar_url: str | None = Field(default=None, max_length=500)
    allowed_library_ids: list[str] | None = Field(default=None)
    maturity_limit: StrictInt | None = Field(default=None, ge=0, le=21)


__all__ = ["CreateProfileRequest", "UpdateProfileRequest"]
