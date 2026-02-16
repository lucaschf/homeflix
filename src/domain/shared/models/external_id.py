"""External ID base class for API exposure.

Format: {prefix}_{base62_random_12chars}
Example: mov_2xK9mPqR7nL4

See ADR-002 for context and decision details.

Specific ID types (MovieId, SeriesId, etc.) are defined in their
respective bounded contexts under value_objects/ids.py.
"""

import secrets
import string
from typing import Any, ClassVar, Self

from pydantic import ConfigDict, model_validator

from src.domain.shared.models.value_object import StringValueObject

BASE62_ALPHABET = string.ascii_letters + string.digits
RANDOM_PART_LENGTH = 12


class ExternalId(StringValueObject):
    """Base class for prefixed external IDs.

    Format: {prefix}_{base62_random_12chars}

    Subclasses must define EXPECTED_PREFIX.
    The generate() method and prefix validation are inherited from this base class.

    Example:
        >>> class MovieId(ExternalId):
        ...     EXPECTED_PREFIX: ClassVar[str] = "mov"
        ...
        >>> movie_id = MovieId.generate()
        >>> movie_id.prefix
        'mov'
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(
        frozen=True,
        str_strip_whitespace=True,
    )

    # Subclasses must override this
    EXPECTED_PREFIX: ClassVar[str] = ""

    root: str

    @classmethod
    def __init_subclass__(cls, **kwargs: Any) -> None:
        """Ensure subclasses define EXPECTED_PREFIX."""
        super().__init_subclass__(**kwargs)  # type: ignore[no-untyped-call]
        if cls is not ExternalId and not cls.EXPECTED_PREFIX:
            raise TypeError(f"{cls.__name__} must define a non-empty EXPECTED_PREFIX")

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

        _prefix, random_part = parts

        if len(random_part) != RANDOM_PART_LENGTH:
            raise ValueError(f"Random part must be {RANDOM_PART_LENGTH} characters")

        if any(c not in BASE62_ALPHABET for c in random_part):
            raise ValueError("Random part must only contain Base62 characters")

        return str(value)

    @model_validator(mode="after")
    def validate_prefix(self) -> Self:
        """Validate that the ID has the expected prefix for this type."""
        if self.prefix != self.EXPECTED_PREFIX:
            raise ValueError(f"{self.__class__.__name__} must have '{self.EXPECTED_PREFIX}' prefix")
        return self

    @classmethod
    def generate(cls) -> Self:
        """Generate a new external ID with the class prefix.

        Returns:
            A new instance with a unique base62 random part.

        Raises:
            TypeError: If called directly on ExternalId base class.
        """
        if cls is ExternalId:
            raise TypeError("generate() must be called on a subclass with EXPECTED_PREFIX defined")
        random_part = "".join(secrets.choice(BASE62_ALPHABET) for _ in range(RANDOM_PART_LENGTH))
        return cls(root=f"{cls.EXPECTED_PREFIX}_{random_part}")

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
    "BASE62_ALPHABET",
    "RANDOM_PART_LENGTH",
    "ExternalId",
]
