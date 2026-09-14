"""DTOs for identity use cases.

Use case inputs and outputs use plain ``str`` for IDs (rather than
domain VOs) so the application layer is callable from any context
(tests, CLI, HTTP routes) without forcing the caller to import
domain VOs. The use cases are responsible for converting str → VO
and validating format at the application boundary.

``role`` is the exception (ADR-018): inputs carry the ``UserRole``
enum, converted/validated at the presentation boundary, so an invalid
role never reaches the use case. Outputs keep ``str`` — they are wire
payloads.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.modules.identity.domain.value_objects.user_role import UserRole


@dataclass(frozen=True)
class ProfileOutput:
    """Full representation of a profile returned to API consumers.

    ``is_kids`` is derived from ``maturity_limit`` (ADR-035) and kept
    on the wire so existing clients keep reading it.
    """

    id: str
    user_id: str
    name: str
    avatar_url: str | None
    is_kids: bool
    maturity_limit: int | None
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

    role: UserRole | None = None
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
    role: UserRole = UserRole.MEMBER


@dataclass(frozen=True)
class UpdateUserRoleInput:
    """Input for ``UpdateUserRoleUseCase``.

    ``acting_admin_id`` lets the use case enforce "last admin"
    semantics: if the call would drop the active-admin count to
    zero (e.g. demoting yourself when you're the only admin) it
    raises ``CannotDemoteLastAdminError``.
    """

    user_id: str
    role: UserRole
    acting_admin_id: str


@dataclass(frozen=True)
class DeleteAdminUserInput:
    """Input for ``DeleteAdminUserUseCase``.

    ``acting_admin_id`` lets the use case enforce "no self-delete"
    and "no demoting the last admin" guards.
    """

    user_id: str
    acting_admin_id: str


@dataclass(frozen=True)
class SetParentalPinInput:
    """Input for ``SetParentalPinUseCase``.

    ``current_password`` and ``pin`` are plaintext secrets, kept out of
    this object's ``repr()``. That masks only the ``repr``: a traceback
    renderer that dumps frame locals can still show the raw values held
    by other frames, such as the framework's request body.
    """

    user_id: str
    current_password: str = field(repr=False)
    pin: str = field(repr=False)


@dataclass(frozen=True)
class RemoveParentalPinInput:
    """Input for ``RemoveParentalPinUseCase``.

    ``current_password`` is a plaintext secret, kept out of ``repr()``.
    """

    user_id: str
    current_password: str = field(repr=False)


@dataclass(frozen=True)
class UnlockParentalInput:
    """Input for ``UnlockParentalUseCase``.

    ``session_token`` identifies the device whose attempts are counted and
    whose unlock window opens. It and ``pin`` are secrets, kept out of
    ``repr()``.
    """

    user_id: str
    session_token: str = field(repr=False)
    pin: str = field(repr=False)


@dataclass(frozen=True)
class LockParentalInput:
    """Input for ``LockParentalUseCase``.

    ``session_token`` identifies the device whose unlock window closes; a
    secret, kept out of ``repr()``.
    """

    session_token: str = field(repr=False)


__all__ = [
    "CreateAdminUserInput",
    "CreateProfileInput",
    "DeleteAdminUserInput",
    "DeleteProfileAvatarInput",
    "DeleteProfileInput",
    "GetUserDetailInput",
    "ListProfilesForUserInput",
    "ListUsersInput",
    "LockParentalInput",
    "ProfileOutput",
    "RemoveParentalPinInput",
    "SetParentalPinInput",
    "SwitchProfileInput",
    "UnlockParentalInput",
    "UpdateProfileInput",
    "UpdateUserRoleInput",
    "UploadProfileAvatarInput",
    "UserDetail",
    "UserSummary",
]
