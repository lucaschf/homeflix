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

    ``avatar_url`` is not a field. The avatar is set only by uploading
    bytes to ``POST /api/v1/profiles/{id}/avatar``, which stores them and
    derives the URL itself (ADR-018 — the boundary validates instead of
    trusting a string). Accepting one from the client let any
    authenticated caller point a profile at an arbitrary third-party
    host, which every household member's picker then fetched on each
    render, handing that host their IP and User-Agent.

    ``is_kids`` is no longer a field either: it is derived from the
    profile's maturity limit (ADR-035). Clients that still send either
    one are not rejected — undeclared fields are ignored — but the value
    is discarded.
    """

    name: str = Field(min_length=1, max_length=50)
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

    ``avatar_url`` and ``is_kids`` are accepted and ignored, as on
    create: the avatar is owned by the upload route and the kids flag is
    derived from the maturity limit. See :class:`CreateProfileRequest`.
    """

    name: str | None = Field(default=None, min_length=1, max_length=50)
    allowed_library_ids: list[str] | None = Field(default=None)
    maturity_limit: StrictInt | None = Field(default=None, ge=0, le=21)


__all__ = ["CreateProfileRequest", "UpdateProfileRequest"]
