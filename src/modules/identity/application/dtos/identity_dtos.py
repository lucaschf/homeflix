"""DTOs for identity use cases.

Use case inputs and outputs use plain ``str`` for IDs (rather than
domain VOs) so the application layer is callable from any context
(tests, CLI, HTTP routes) without forcing the caller to import
domain VOs. The use cases are responsible for converting str → VO
and validating format at the application boundary.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProfileOutput:
    """Full representation of a profile returned to API consumers."""

    id: str
    user_id: str
    name: str
    avatar_url: str | None
    is_kids: bool
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class CreateProfileInput:
    """Input for ``CreateProfileUseCase``.

    ``user_id`` is the caller's prefixed external ID; the use case
    creates a profile owned by that user.
    """

    user_id: str
    name: str
    is_kids: bool = False
    avatar_url: str | None = None


@dataclass(frozen=True)
class ListProfilesForUserInput:
    """Input for ``ListProfilesForUserUseCase``."""

    user_id: str


@dataclass(frozen=True)
class UpdateProfileInput:
    """Input for ``UpdateProfileUseCase``.

    All fields after ``profile_id`` are optional — only supplied
    fields are updated; omitted fields retain their current value.
    ``avatar_url=None`` is **not** treated as "clear the avatar"; use
    a sentinel-typed payload at the route layer if explicit clearing
    is needed.
    """

    user_id: str
    profile_id: str
    name: str | None = None
    is_kids: bool | None = None
    avatar_url: str | None = None


@dataclass(frozen=True)
class DeleteProfileInput:
    """Input for ``DeleteProfileUseCase``."""

    user_id: str
    profile_id: str


@dataclass(frozen=True)
class SwitchProfileInput:
    """Input for ``SwitchProfileUseCase``.

    ``session_token`` is the opaque value carried by the session
    cookie — passed through from the route's request handler so the
    use case can update the right ``access_tokens`` row.
    """

    user_id: str
    target_profile_id: str
    session_token: str


__all__ = [
    "CreateProfileInput",
    "DeleteProfileInput",
    "ListProfilesForUserInput",
    "ProfileOutput",
    "SwitchProfileInput",
    "UpdateProfileInput",
]
