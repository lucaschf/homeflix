"""Identity bounded context exceptions.

Domain- and application-level errors specific to identity. Reuses the
shared exception bases from ``building_blocks`` so the global handler
maps them to the correct HTTP status without per-BC wiring.
"""

from dataclasses import dataclass

from src.building_blocks.application.errors import (
    ApplicationException,
    ForbiddenOperationException,
    ResourceNotFoundException,
    UnauthorizedOperationException,
)
from src.modules.identity.domain.rule_codes import IdentityRuleCodes


@dataclass
class ProfileNotFoundException(ResourceNotFoundException):
    """The requested profile does not exist (or is soft-deleted).

    Maps to HTTP 404.
    """

    code: str = "PROFILE_NOT_FOUND"
    message_code: str = IdentityRuleCodes.PROFILE_NOT_FOUND
    resource_type: str = "Profile"


@dataclass
class ProfileOwnershipViolation(ForbiddenOperationException):
    """Authenticated user attempted to act on a profile they do not own.

    Maps to HTTP 403. Raised by ``UpdateProfileUseCase``,
    ``DeleteProfileUseCase`` and ``SwitchProfileUseCase`` when the
    target profile's ``user_id`` does not match the caller.
    """

    code: str = "PROFILE_OWNERSHIP_VIOLATION"
    message_code: str = IdentityRuleCodes.PROFILE_OWNERSHIP_VIOLATION


@dataclass
class CannotDeleteLastProfileError(ApplicationException):
    """User attempted to delete their final remaining profile.

    Every authenticated user must have at least one profile so that
    ``get_current_profile`` always has something to resolve. Raised by
    ``DeleteProfileUseCase``. Maps to HTTP 409 (conflict) — distinct
    from a generic 400 because the request is well-formed but conflicts
    with a domain invariant. Status registered in
    ``modules/identity/presentation/error_mapping.py`` (ADR-012).
    """

    code: str = "CANNOT_DELETE_LAST_PROFILE"
    message_code: str = IdentityRuleCodes.CANNOT_DELETE_LAST_PROFILE


@dataclass
class NoActiveSessionError(UnauthorizedOperationException):
    """The request has no session cookie, so no current profile can be resolved.

    Maps to HTTP 401. Raised by the ``get_current_profile`` dependency
    when the cookie is missing or the cookie's token is unknown.
    """

    code: str = "NO_ACTIVE_SESSION"
    message_code: str = IdentityRuleCodes.NO_ACTIVE_SESSION


@dataclass
class NoActiveProfileSelectedError(ApplicationException):
    """The session is valid but the user has not selected a profile yet.

    Returned as HTTP 409 (conflict) so the frontend can distinguish "not
    logged in" (401) from "logged in but profile picker required" (409).
    Raised by ``get_current_profile``. Status registered in
    ``modules/identity/presentation/error_mapping.py`` (ADR-012).
    """

    code: str = "NO_ACTIVE_PROFILE"
    message_code: str = IdentityRuleCodes.NO_ACTIVE_PROFILE


@dataclass
class UserNotFoundException(ResourceNotFoundException):
    """The requested user does not exist (or is soft-deleted).

    Maps to HTTP 404. Raised by the admin user use cases when the
    path id doesn't resolve to a live user.
    """

    code: str = "USER_NOT_FOUND"
    message_code: str = IdentityRuleCodes.USER_NOT_FOUND
    resource_type: str = "User"


@dataclass
class UserEmailAlreadyExistsError(ApplicationException):
    """Admin tried to create a user with an email already in the table.

    Maps to HTTP 409 (conflict). The check covers active rows AND
    soft-deleted tombstones because the underlying ``email`` column
    is unique at the DB level and a re-insert would crash.
    """

    code: str = "USER_EMAIL_ALREADY_EXISTS"
    message_code: str = IdentityRuleCodes.USER_EMAIL_ALREADY_EXISTS


@dataclass
class CannotDeleteSelfError(ApplicationException):
    """Admin tried to delete their own user account.

    Maps to HTTP 409. The UI also hides the delete button on the
    self row, but the server-side guard is the source of truth — a
    direct curl call still gets refused.
    """

    code: str = "USER_CANNOT_DELETE_SELF"
    message_code: str = IdentityRuleCodes.USER_CANNOT_DELETE_SELF


@dataclass
class CannotDemoteLastAdminError(ApplicationException):
    """Operation would leave the system with zero active admins.

    Maps to HTTP 409. Fires from both the role-flip (demoting the
    last admin) and the delete (removing the last admin even when
    not self-targeting) paths.
    """

    code: str = "USER_CANNOT_DEMOTE_LAST_ADMIN"
    message_code: str = IdentityRuleCodes.USER_CANNOT_DEMOTE_LAST_ADMIN


__all__ = [
    "CannotDeleteLastProfileError",
    "CannotDeleteSelfError",
    "CannotDemoteLastAdminError",
    "NoActiveProfileSelectedError",
    "NoActiveSessionError",
    "ProfileNotFoundException",
    "ProfileOwnershipViolation",
    "UserEmailAlreadyExistsError",
    "UserNotFoundException",
]
