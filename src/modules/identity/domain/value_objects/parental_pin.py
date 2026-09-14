"""Parental PIN value object (ADR-035, Amendment 7 D4)."""

import re
from typing import Any, ClassVar

from pydantic import model_validator

from src.building_blocks.domain.errors import DomainValidationException
from src.building_blocks.domain.value_objects import StringValueObject
from src.modules.identity.domain.rule_codes import IdentityRuleCodes

# ASCII digits only: ``str.isdigit()`` and ``\d`` also accept other Unicode
# digits (Arabic-Indic, fullwidth). Matched with ``fullmatch`` because
# ``$`` alone lets a trailing newline through.
_PIN_REGEX = re.compile(r"^[0-9]{6}$")

_INVALID_MESSAGE = (
    f"Parental PIN must be exactly 6 digits [{IdentityRuleCodes.PARENTAL_PIN_INVALID_FORMAT}]"
)

_MASK = "******"


class ParentalPin(StringValueObject):
    """The household's parental PIN, in plaintext, on its way to the hasher.

    Exactly six ASCII digits (ADR-035, Amendment 7 D4); nothing is trimmed
    or normalised, so ``" 123456"`` is rejected rather than silently
    becoming another PIN.

    The value is a secret for its whole short life:

    - ``repr()`` and ``str()`` are masked, so the PIN does not reach a log
      line or a traceback's locals through this object;
    - an invalid value raises a ``DomainValidationException`` that carries
      neither the value nor the Pydantic error behind it. The generic
      conversion (``DomainValidationException.from_pydantic_errors``) puts
      the raw input in ``details[].metadata.input``, which the exception
      handler would echo in the 422 body.

    Only ``.value`` exposes the digits, for the password hasher.

    Example:
        >>> ParentalPin("042917").value
        '042917'
        >>> ParentalPin("042917")
        ParentalPin(******)
    """

    LENGTH: ClassVar[int] = 6

    def __init__(self, root: Any = None, /, **data: Any) -> None:
        try:
            super().__init__(root, **data)
        except DomainValidationException:
            # ``from None`` drops the chained Pydantic error, whose text
            # includes ``input_value=...``.
            raise DomainValidationException(
                message=_INVALID_MESSAGE,
                message_code=IdentityRuleCodes.PARENTAL_PIN_INVALID_FORMAT,
                object_type="ParentalPin",
            ) from None

    @model_validator(mode="before")
    @classmethod
    def validate_pin(cls, value: object) -> str:
        """Accept exactly six ASCII digits and nothing else."""
        if not isinstance(value, str) or _PIN_REGEX.fullmatch(value) is None:
            raise ValueError(_INVALID_MESSAGE)
        return value

    def __str__(self) -> str:
        """Return a mask instead of the digits."""
        return _MASK

    def __repr__(self) -> str:
        """Return a representation with the digits masked."""
        return f"{self.__class__.__name__}({_MASK})"


__all__ = ["ParentalPin"]
