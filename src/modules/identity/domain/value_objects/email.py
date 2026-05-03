"""Email value object."""

import re
from typing import ClassVar

from pydantic import model_validator

from src.building_blocks.domain.value_objects import StringValueObject
from src.modules.identity.domain.rule_codes import IdentityRuleCodes

# Simplified RFC 5322 regex: local@domain with at least one dot in domain.
# Intentionally NOT exhaustive (full RFC 5322 is impractical to validate
# with regex). Catches the common malformed cases without dragging in the
# `email-validator` runtime dependency.
_EMAIL_REGEX = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")


class Email(StringValueObject):
    """User email address.

    Constraints:
        - Trimmed and lowercased on construction (case-insensitive).
        - Must match a simplified RFC 5322 format.
        - Maximum 320 characters (RFC 5321 SMTP limit).

    The hashed password lives on the SQLAlchemy ``UserModel`` (FastAPI
    Users owns it). Email is the only credential surface owned by the
    domain.

    Example:
        >>> Email("Foo@Example.COM").value
        'foo@example.com'
        >>> Email("  user@host.io  ").value
        'user@host.io'
    """

    MAX_LENGTH: ClassVar[int] = 320

    @model_validator(mode="before")
    @classmethod
    def normalize_and_validate(cls, value: object) -> str:
        """Normalize (trim + lowercase) and validate the email format."""
        if not isinstance(value, str):
            # Defensive guard against programmer error; user-submitted JSON
            # always arrives as a string before reaching this validator. No
            # rule code — i18n only covers content-level violations (matches
            # the pattern in library/value_objects/library_name.py).
            raise ValueError("Email must be a string")

        normalized = value.strip().lower()

        if not normalized:
            raise ValueError(f"Email cannot be empty [{IdentityRuleCodes.EMAIL_EMPTY}]")

        if len(normalized) > cls.MAX_LENGTH:
            raise ValueError(
                f"Email cannot exceed {cls.MAX_LENGTH} characters "
                f"[{IdentityRuleCodes.EMAIL_TOO_LONG}]"
            )

        if not _EMAIL_REGEX.fullmatch(normalized):
            raise ValueError(
                f"Email must be in valid format " f"[{IdentityRuleCodes.EMAIL_INVALID_FORMAT}]"
            )

        return normalized


__all__ = ["Email"]
