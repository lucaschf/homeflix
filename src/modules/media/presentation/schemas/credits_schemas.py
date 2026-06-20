"""Request schemas for credits-marker endpoints."""

from pydantic import BaseModel, Field


class SetCreditsRequest(BaseModel):
    """Request body for ``PUT /admin/media/{media_id}/credits``.

    The ``start_seconds <= duration`` invariant is enforced by the domain
    layer; only the lower bound lives here so malformed payloads fail
    fast with a 422 before the use case runs.

    Attributes:
        start_seconds: Onset of the end credits, in seconds.
    """

    start_seconds: int = Field(ge=0)


__all__ = ["SetCreditsRequest"]
