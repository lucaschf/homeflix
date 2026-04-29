"""Request schemas for episode intro-marker endpoints."""

from pydantic import BaseModel, Field


class SetIntroRequest(BaseModel):
    """Request body for ``PUT /episodes/{id}/intro``.

    Cross-field invariants (``end > start``, ``end <= duration``) are
    enforced by the domain layer; only basic per-field bounds live here
    so malformed payloads fail fast with a 422 before the use case runs.

    Attributes:
        start_seconds: Offset from the start of the episode (seconds).
        end_seconds: Offset from the start of the episode (seconds).
    """

    start_seconds: int = Field(ge=0)
    end_seconds: int = Field(ge=1)


__all__ = ["SetIntroRequest"]
