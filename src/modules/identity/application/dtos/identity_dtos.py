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
from enum import StrEnum

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
class MaturityLimitChange:
    """A requested change to a profile's maturity limit.

    Wrapped so an update can tell "leave the limit alone" (no change at
    all) from "remove the limit" (a change to ``None``).

    Attributes:
        value: The new limit in years (0 to 21), or ``None`` to make the
            profile unrestricted.
    """

    value: int | None


@dataclass(frozen=True)
class CreateProfileInput:
    """Input for ``CreateProfileUseCase``.

    ``user_id`` is the caller's prefixed external ID; the use case
    creates a profile owned by that user.

    ``allowed_library_ids`` defaults to ``None`` meaning "use the
    aggregate's default" (an empty list — the ACL is default-deny).
    Pass an explicit list at creation time to grant access right
    away.

    ``maturity_limit`` is the new profile's limit in years, or ``None``
    for unrestricted (ADR-035). ``session_token`` identifies the device
    the parental gate reads and whose unlock a gated creation spends; a
    secret, kept out of ``repr()``. ``None`` means the call runs outside a
    session, such as an operator script: the gate then has no unlock to
    spend and treats the session as the strictest one.
    """

    user_id: str
    name: str
    allowed_library_ids: list[str] | None = None
    maturity_limit: int | None = None
    session_token: str | None = field(default=None, repr=False)


@dataclass(frozen=True)
class ListProfilesForUserInput:
    """Input for ``ListProfilesForUserUseCase``."""

    user_id: str


@dataclass(frozen=True)
class UpdateProfileInput:
    """Input for ``UpdateProfileUseCase``.

    All fields after ``profile_id`` are optional — only supplied
    fields are updated; omitted fields retain their current value.

    There is no ``avatar_url``: the avatar is written only by
    ``UploadProfileAvatarUseCase`` / ``DeleteProfileAvatarUseCase``, from
    a URL ``AvatarStoragePort`` produced, so no caller can store one of
    its own choosing.

    ``allowed_library_ids=None`` follows the same omitted-vs-cleared
    convention: ``None`` means "don't touch the ACL"; an explicit
    empty list ``[]`` means "revoke access to every library".

    ``maturity_limit=None`` also means "don't touch the limit"; removing
    the limit is ``MaturityLimitChange(None)``. ``session_token`` is as on
    :class:`CreateProfileInput`.
    """

    user_id: str
    profile_id: str
    name: str | None = None
    allowed_library_ids: list[str] | None = None
    maturity_limit: MaturityLimitChange | None = None
    session_token: str | None = field(default=None, repr=False)


@dataclass(frozen=True)
class DeleteProfileInput:
    """Input for ``DeleteProfileUseCase``.

    ``session_token`` is as on :class:`CreateProfileInput`.
    """

    user_id: str
    profile_id: str
    session_token: str | None = field(default=None, repr=False)


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


class AdminAccessLevel(StrEnum):
    """What administrator authority a session holds right now (ADR-035).

    ``NONE`` for an account without the admin role; for an administrator,
    ``GRANTED`` or ``SUSPENDED`` as the parental gate decides.
    """

    NONE = "none"
    GRANTED = "granted"
    SUSPENDED = "suspended"


@dataclass(frozen=True)
class GetAdminAccessInput:
    """Input for ``GetAdminAccessUseCase`` and ``EnsureAdminAuthorityUseCase``.

    ``role`` and ``parental_pin_configured`` come from the account the
    request already authenticated, so the use case never reads it again.
    ``session_token`` identifies the device whose selected profile and
    unlock window count; a secret, kept out of ``repr()``. ``is_write`` says
    whether the request changes state (Amendment 7 D10).
    """

    user_id: str
    role: UserRole
    parental_pin_configured: bool
    session_token: str = field(repr=False)
    is_write: bool = False


__all__ = [
    "AdminAccessLevel",
    "CreateAdminUserInput",
    "CreateProfileInput",
    "DeleteAdminUserInput",
    "DeleteProfileAvatarInput",
    "DeleteProfileInput",
    "GetAdminAccessInput",
    "GetUserDetailInput",
    "ListProfilesForUserInput",
    "ListUsersInput",
    "LockParentalInput",
    "MaturityLimitChange",
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
