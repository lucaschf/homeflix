"""External ID base class for API exposure.

Format: {prefix}_{base62_random_12chars}
Example: mov_2xK9mPqR7nL4

See ADR-002 for context and decision details.

Specific ID types (MovieId, SeriesId, etc.) are defined in their
respective bounded contexts under value_objects/ids.py.
"""

import secrets
import string
from typing import Any, ClassVar

from pydantic import ConfigDict, RootModel, ValidationError, model_validator

from src.domain.shared.models.value_object import StringValueObject
from src.domain.shared.models.domain_model import DomainValidationError
from src.domain.shared.models.value_object import ValueObject

BASE62_ALPHABET = string.ascii_letters + string.digits
RANDOM_PART_LENGTH = 12


class ExternalId(StringValueObject, ValueObject):
    """Base class for prefixed external IDs.

    Format: {prefix}_{base62_random_12chars}

    Subclasses should define EXPECTED_PREFIX and override generate().

    Example:
        >>> class MovieId(ExternalId):
        ...     EXPECTED_PREFIX: ClassVar[str] = "mov"
        ...
        ...     @classmethod
        ...     def generate(cls) -> "MovieId":
        ...         return cls._generate_with_prefix(cls.EXPECTED_PREFIX)
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(
        frozen=True,
        str_strip_whitespace=True,
        extra=None,
    )

    # Subclasses should override this
    EXPECTED_PREFIX: ClassVar[str] = ""

    root: str

    def __init__(self, root: Any = None, /, **data: Any) -> None:
        """Initialize an ExternalId from a string value."""
        try:
            if root is not None:
                RootModel.__init__(self, root)
            else:
                RootModel.__init__(self, **data)
        except ValidationError as e:
            raise DomainValidationError.from_pydantic(e) from e

    @model_validator(mode="before")
    @classmethod
    def validate_format(cls, value: Any) -> str:
        """Validate the external ID format."""
        if not isinstance(value, str):
            raise ValueError("External ID must be a string")

        value = value.strip()

        if "_" not in value:
            raise ValueError(f"External ID must contain underscore separator: {value}")

        parts = value.split("_", 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid external ID format: {value}")

        prefix, random_part = parts

        if len(random_part) != RANDOM_PART_LENGTH:
            raise ValueError(f"Random part must be {RANDOM_PART_LENGTH} characters")

        if any(c not in BASE62_ALPHABET for c in random_part):
            raise ValueError("Random part must only contain Base62 characters")

        return value

    @classmethod
    def _generate_with_prefix(cls, prefix: str) -> "ExternalId":
        """Generate a new external ID with the given prefix.

        This is a helper for subclasses to use in their generate() method.
        """
        random_part = "".join(
            secrets.choice(BASE62_ALPHABET) for _ in range(RANDOM_PART_LENGTH)
        )
        return cls(f"{prefix}_{random_part}")

    @property
    def value(self) -> str:
        """Get the full ID string."""
        return self.root

    @property
    def prefix(self) -> str:
        """Get the prefix part of the ID."""
        return self.root.split("_")[0]

    @property
    def random_part(self) -> str:
        """Get the random part of the ID."""
        return self.root.split("_")[1]

    def __str__(self) -> str:
        """Return the ID as a string."""
        return self.value

    def __repr__(self) -> str:
        """Return a detailed string representation."""
        return f"{self.__class__.__name__}({self.value!r})"

    def __eq__(self, other: object) -> bool:
        """Check equality with another ExternalId."""
        if not isinstance(other, ExternalId):
            return NotImplemented
        return self.value == other.value

    def __hash__(self) -> int:
        """Return hash for use in sets and dicts."""
        return hash((self.__class__.__name__, self.value))


__all__ = [
    "ExternalId",
    "BASE62_ALPHABET",
    "RANDOM_PART_LENGTH",
]
