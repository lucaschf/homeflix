"""Share token value object for custom lists."""

import secrets
from typing import ClassVar

from pydantic import model_validator

from src.building_blocks.domain.value_objects import StringValueObject

# Bytes of entropy behind the token. ``token_urlsafe(24)`` yields a
# 32-char base64url string — unguessable and comfortably below the
# column width. Kept well above a sequential/short id (edge case 7).
_ENTROPY_BYTES = 24


class ShareToken(StringValueObject):
    """An opaque, unguessable secret that grants read access to a list.

    Presence of a token on a :class:`CustomList` means the list is
    shared; clearing it revokes sharing. The value carries no structure
    a client should parse — it is a bearer secret, minted server-side
    via :meth:`generate` and matched verbatim on lookup.

    Unlike an :class:`~src.building_blocks.domain.external_id.ExternalId`
    it is deliberately *not* prefixed or base62-shaped: it is a secret,
    not a resource identifier, so it must not be predictable from any
    public id.

    Constraints:
        - Trimmed; must be at least ``MIN_LENGTH`` characters so a
          truncated or empty value can never slip through as a valid
          token.

    Example:
        >>> token = ShareToken.generate()
        >>> len(token.value) >= ShareToken.MIN_LENGTH
        True
    """

    MIN_LENGTH: ClassVar[int] = 20
    MAX_LENGTH: ClassVar[int] = 64

    @model_validator(mode="before")
    @classmethod
    def validate_token(cls, value: object) -> str:
        """Trim and validate the token's shape."""
        if not isinstance(value, str):
            raise ValueError("Share token must be a string")
        trimmed = value.strip()
        if len(trimmed) < cls.MIN_LENGTH:
            raise ValueError(f"Share token must be at least {cls.MIN_LENGTH} characters")
        if len(trimmed) > cls.MAX_LENGTH:
            raise ValueError(f"Share token cannot exceed {cls.MAX_LENGTH} characters")
        return trimmed

    @classmethod
    def generate(cls) -> "ShareToken":
        """Mint a fresh, cryptographically-random token.

        Returns:
            A new :class:`ShareToken` backed by
            ``secrets.token_urlsafe`` — safe to hand out in a URL.
        """
        return cls(secrets.token_urlsafe(_ENTROPY_BYTES))


__all__ = ["ShareToken"]
