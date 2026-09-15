"""Identity domain-level exceptions.

Only genuine domain-invariant violations raised **from the domain layer**
live here (subclassing the domain exception bases). Application-level errors
(not-found, forbidden, unauthorized, conflict) raised by the use cases live
in ``identity/application/errors.py`` — keeping the domain layer free of any
dependency on ``building_blocks.application``.

The parental-control errors (ADR-035) live here too: they are the outcomes
of the ``ParentalGate`` rules, which the admin and profile gates consume.
Every one of them maps to 403 or 409 — never 401, which the web client reads
as an expired session and answers by signing the user out.
"""

import math
from dataclasses import dataclass
from datetime import datetime

from src.building_blocks.domain.errors import BusinessRuleViolationException, ExceptionDetail
from src.modules.identity.domain.rule_codes import IdentityRuleCodes


@dataclass
class CannotDemoteLastAdminError(BusinessRuleViolationException):
    """Operation would leave the system with zero active admins.

    A domain invariant — the household must always retain at least one
    active administrator — enforced by the ``admin_quorum`` domain service.
    Fires from both the role-flip (demoting the last admin) and the delete
    (removing the last admin even when not self-targeting) paths.

    Maps to HTTP 409 via ``error_mapping.py`` (keyed on ``code``, ADR-012),
    unchanged by the domain re-base.
    """

    code: str = "USER_CANNOT_DEMOTE_LAST_ADMIN"
    message_code: str = IdentityRuleCodes.USER_CANNOT_DEMOTE_LAST_ADMIN
    rule_code: str = IdentityRuleCodes.USER_CANNOT_DEMOTE_LAST_ADMIN


@dataclass
class ParentalPinRequiredError(BusinessRuleViolationException):
    """The operation needs a valid parental unlock on this session.

    Raised by the gates that consume the unlock window (ADR-035, decisions
    8 and 9). The client answers it by asking for the PIN. Maps to HTTP 403.
    """

    code: str = "PARENTAL_PIN_REQUIRED"
    message_code: str = IdentityRuleCodes.PARENTAL_PIN_REQUIRED
    rule_code: str = IdentityRuleCodes.PARENTAL_PIN_REQUIRED


@dataclass
class ParentalPinInvalidError(BusinessRuleViolationException):
    """The parental PIN entered does not match the account's PIN.

    The attempt has already been counted against this session's lockout
    budget. Maps to HTTP 403.
    """

    code: str = "PARENTAL_PIN_INVALID"
    message_code: str = IdentityRuleCodes.PARENTAL_PIN_INVALID
    rule_code: str = IdentityRuleCodes.PARENTAL_PIN_INVALID


@dataclass
class ParentalPinLockedError(BusinessRuleViolationException):
    """This session is locked out of PIN attempts (ADR-035, Amendment 7 D4).

    Raised when a lock is in force — the PIN is not even checked — and
    when a wrong PIN is the attempt that starts the lock, so the client can
    show the countdown at once. Maps to HTTP 403.

    ``retry_after_seconds`` travels in ``details[0].metadata``: the response
    body only carries ``message``, ``code`` and ``details``, so a value put
    in ``tags`` or ``message_params`` would never reach the client.

    Attributes:
        retry_after_seconds: Whole seconds until the lock ends, or ``None``
            when unknown.

    Example:
        >>> raise ParentalPinLockedError.until(locked_until, now=now)
    """

    code: str = "PARENTAL_PIN_LOCKED"
    message_code: str = IdentityRuleCodes.PARENTAL_PIN_LOCKED
    rule_code: str = IdentityRuleCodes.PARENTAL_PIN_LOCKED
    retry_after_seconds: int | None = None

    def __post_init__(self) -> None:
        """Expose the wait as an i18n param and as the response details."""
        super().__post_init__()
        self.message_params = {"retry_after_seconds": self.retry_after_seconds}
        if self.retry_after_seconds is not None:
            # Assigned, not appended: ``with_translation`` rebuilds the
            # instance through ``dataclasses.replace``, which re-runs this.
            self.details = [
                ExceptionDetail(
                    code=self.code,
                    message=f"Try again in {self.retry_after_seconds} seconds",
                    metadata={"retry_after_seconds": self.retry_after_seconds},
                )
            ]

    @classmethod
    def until(cls, locked_until: datetime, *, now: datetime) -> "ParentalPinLockedError":
        """Build the error for a lock that ends at ``locked_until``.

        Args:
            locked_until: When the lock ends.
            now: The current time, on the same clock.

        Returns:
            ParentalPinLockedError whose wait is rounded up to whole seconds,
            so a client that waits exactly that long finds the lock over.
        """
        remaining = math.ceil((locked_until - now).total_seconds())
        return cls(
            message="Too many wrong parental PIN attempts on this device",
            retry_after_seconds=max(remaining, 0),
        )


@dataclass
class ParentalPinNotConfiguredError(BusinessRuleViolationException):
    """The account has no parental PIN, so there is nothing to unlock with.

    Maps to HTTP 409.
    """

    code: str = "PARENTAL_PIN_NOT_CONFIGURED"
    message_code: str = IdentityRuleCodes.PARENTAL_PIN_NOT_CONFIGURED
    rule_code: str = IdentityRuleCodes.PARENTAL_PIN_NOT_CONFIGURED


@dataclass
class ParentalPinInUseError(BusinessRuleViolationException):
    """The parental PIN cannot be removed while a profile still has a limit.

    ADR-035, Amendment 7 D2: with no PIN, no limit could be protected. Maps
    to HTTP 409.
    """

    code: str = "PARENTAL_PIN_IN_USE"
    message_code: str = IdentityRuleCodes.PARENTAL_PIN_IN_USE
    rule_code: str = IdentityRuleCodes.PARENTAL_PIN_IN_USE


__all__ = [
    "CannotDemoteLastAdminError",
    "ParentalPinInUseError",
    "ParentalPinInvalidError",
    "ParentalPinLockedError",
    "ParentalPinNotConfiguredError",
    "ParentalPinRequiredError",
]
