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


__all__ = [
    "CannotDeleteLastProfileError",
    "NoActiveProfileSelectedError",
    "NoActiveSessionError",
    "ProfileNotFoundException",
    "ProfileOwnershipViolation",
]
