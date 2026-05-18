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
    allowed_library_ids: list[str]
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class CreateProfileInput:
    """Input for ``CreateProfileUseCase``.

    ``user_id`` is the caller's prefixed external ID; the use case
    creates a profile owned by that user.

    ``allowed_library_ids`` defaults to ``None`` meaning "use the
    aggregate's default" (an empty list — the ACL is default-deny).
    Pass an explicit list at creation time to grant access right
    away.
    """

    user_id: str
    name: str
    is_kids: bool = False
    avatar_url: str | None = None
    allowed_library_ids: list[str] | None = None


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

    ``allowed_library_ids=None`` follows the same omitted-vs-cleared
    convention: ``None`` means "don't touch the ACL"; an explicit
    empty list ``[]`` means "revoke access to every library".
    """

    user_id: str
    profile_id: str
    name: str | None = None
    is_kids: bool | None = None
    avatar_url: str | None = None
    allowed_library_ids: list[str] | None = None


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


@dataclass(frozen=True)
class UploadProfileAvatarInput:
    """Input for ``UploadProfileAvatarUseCase``.

    Bytes + declared MIME come from the multipart upload at the
    route boundary; the route enforces ownership before this DTO
    is constructed (caller's ``user_id`` must own the profile).
    """

    user_id: str
    profile_id: str
    content: bytes
    declared_mime_type: str


@dataclass(frozen=True)
class DeleteProfileAvatarInput:
    """Input for ``DeleteProfileAvatarUseCase``."""

    user_id: str
    profile_id: str


# ─── Admin user surface ────────────────────────────────────


@dataclass(frozen=True)
class UserSummary:
    """Lightweight user row for the admin list page.

    Excludes hashed_password and other secrets; ``profile_count`` is
    computed via a per-row aggregate so the admin can eyeball
    multi-profile households without opening each detail.
    """

    id: str
    email: str
    role: str
    is_active: bool
    profile_count: int
    created_at: str


@dataclass(frozen=True)
class UserDetail:
    """Full payload for the admin user-detail page.

    Includes the user's profile list (read-only in P3) so the
    operator can see ACL grants without a second round-trip.
    """

    id: str
    email: str
    role: str
    is_active: bool
    created_at: str
    updated_at: str
    profiles: list[ProfileOutput]


@dataclass(frozen=True)
class ListUsersInput:
    """Input for ``ListUsersUseCase``."""

    role: str | None = None
    limit: int = 50
    offset: int = 0


@dataclass(frozen=True)
class GetUserDetailInput:
    """Input for ``GetUserDetailUseCase``."""

    user_id: str


@dataclass(frozen=True)
class CreateAdminUserInput:
    """Input for ``CreateAdminUserUseCase``.

    The admin types the email + initial password; the user is
    expected to change the password from ``/settings`` after their
    first login. ``role`` defaults to ``MEMBER`` — promoting a
    fresh account to admin is an explicit choice the operator has
    to make on the create form.
    """

    email: str
    password: str
    role: str = "member"


@dataclass(frozen=True)
class UpdateUserRoleInput:
    """Input for ``UpdateUserRoleUseCase``.

    ``acting_admin_id`` lets the use case enforce "last admin"
    semantics: if the call would drop the active-admin count to
    zero (e.g. demoting yourself when you're the only admin) it
    raises ``CannotDemoteLastAdminError``.
    """

    user_id: str
    role: str
    acting_admin_id: str


@dataclass(frozen=True)
class DeleteAdminUserInput:
    """Input for ``DeleteAdminUserUseCase``.

    ``acting_admin_id`` lets the use case enforce "no self-delete"
    and "no demoting the last admin" guards.
    """

    user_id: str
    acting_admin_id: str


__all__ = [
    "CreateAdminUserInput",
    "CreateProfileInput",
    "DeleteAdminUserInput",
    "DeleteProfileAvatarInput",
    "DeleteProfileInput",
    "GetUserDetailInput",
    "ListProfilesForUserInput",
    "ListUsersInput",
    "ProfileOutput",
    "SwitchProfileInput",
    "UpdateProfileInput",
    "UpdateUserRoleInput",
    "UploadProfileAvatarInput",
    "UserDetail",
    "UserSummary",
]
