"""Base classes for Value Objects.

Value Objects are immutable objects identified by their value, not identity.
"""

from datetime import date
from typing import Any, ClassVar

from pydantic import ConfigDict, RootModel, ValidationError

from src.domain.shared.exceptions.domain import DomainValidationException
from src.domain.shared.models.domain_model import DomainModel


class ValueObject(DomainModel):
    """Base class for Value Objects.

    Value Objects MUST be immutable (frozen=True).
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(
        frozen=True,
        validate_assignment=True,
        extra="forbid",
    )

    def __init__(self, /, **data: Any) -> None:
        super().__init__(**data)
        self._ensure_immutability()

    def _ensure_immutability(self) -> None:
        """Ensure the Value Object is frozen (immutable)."""
        frozen_config = self.model_config.get("frozen", False)
        if not isinstance(frozen_config, bool) or not frozen_config:
            raise ValueError("Value Objects must be immutable (frozen=True)")


class StringValueObject(RootModel[str], ValueObject):
    """Base class for Value Objects wrapping a single string value."""

    model_config: ClassVar[ConfigDict] = ConfigDict(
        frozen=True,
        str_strip_whitespace=True,
        extra=None,
    )

    root: str

    def __init__(self, root: Any = None, /, **data: Any) -> None:
        try:
            if root is not None:
                RootModel.__init__(self, root)
            else:
                RootModel.__init__(self, **data)
        except ValidationError as e:
            raise DomainValidationException.from_pydantic_errors(
                object_type=self.__class__.__name__,
                pydantic_errors=e.errors(),
            ) from e

    @property
    def value(self) -> str:
        """Return the wrapped string value."""
        return self.root

    def __str__(self) -> str:
        """Return the string value."""
        return self.value

    def __repr__(self) -> str:
        """Return a detailed string representation."""
        return f"{self.__class__.__name__}({self.value!r})"

    def __eq__(self, other: object) -> bool:
        """Check equality with another StringValueObject of the same type."""
        if not isinstance(other, self.__class__):
            return NotImplemented
        return self.value == other.value

    def __hash__(self) -> int:
        """Return hash for use in sets and dicts."""
        return hash((self.__class__, self.value))


class IntValueObject(RootModel[int], ValueObject):
    """Base class for Value Objects wrapping a single integer value."""

    model_config: ClassVar[ConfigDict] = ConfigDict(
        frozen=True,
        extra=None,
    )

    root: int

    def __init__(self, root: Any = None, /, **data: Any) -> None:
        try:
            if root is not None:
                RootModel.__init__(self, root)
            else:
                RootModel.__init__(self, **data)
        except ValidationError as e:
            raise DomainValidationException.from_pydantic_errors(
                object_type=self.__class__.__name__,
                pydantic_errors=e.errors(),
            ) from e

    @property
    def value(self) -> int:
        """Return the wrapped integer value."""
        return self.root

    def __str__(self) -> str:
        """Return the string representation of the integer value."""
        return str(self.value)

    def __repr__(self) -> str:
        """Return a detailed string representation."""
        return f"{self.__class__.__name__}({self.value!r})"

    def __eq__(self, other: object) -> bool:
        """Check equality with another IntValueObject of the same type."""
        if not isinstance(other, self.__class__):
            return NotImplemented
        return self.value == other.value

    def __hash__(self) -> int:
        """Return hash for use in sets and dicts."""
        return hash((self.__class__, self.value))

    def __lt__(self, other: object) -> bool:
        """Check if this value is less than another."""
        if not isinstance(other, self.__class__):
            return NotImplemented
        return self.value < other.value

    def __le__(self, other: object) -> bool:
        """Check if this value is less than or equal to another."""
        if not isinstance(other, self.__class__):
            return NotImplemented
        return self.value <= other.value

    def __gt__(self, other: object) -> bool:
        """Check if this value is greater than another."""
        if not isinstance(other, self.__class__):
            return NotImplemented
        return self.value > other.value

    def __ge__(self, other: object) -> bool:
        """Check if this value is greater than or equal to another."""
        if not isinstance(other, self.__class__):
            return NotImplemented
        return self.value >= other.value


class FloatValueObject(RootModel[float], ValueObject):
    """Base class for Value Objects wrapping a single float value."""

    model_config: ClassVar[ConfigDict] = ConfigDict(
        frozen=True,
        extra=None,
    )

    root: float

    def __init__(self, root: Any = None, /, **data: Any) -> None:
        try:
            if root is not None:
                RootModel.__init__(self, root)
            else:
                RootModel.__init__(self, **data)
        except ValidationError as e:
            raise DomainValidationException.from_pydantic_errors(
                object_type=self.__class__.__name__,
                pydantic_errors=e.errors(),
            ) from e

    @property
    def value(self) -> float:
        """Return the wrapped float value."""
        return self.root

    def __str__(self) -> str:
        """Return the string representation of the float value."""
        return str(self.value)

    def __repr__(self) -> str:
        """Return a detailed string representation."""
        return f"{self.__class__.__name__}({self.value!r})"

    def __eq__(self, other: object) -> bool:
        """Check equality with another FloatValueObject of the same type."""
        if not isinstance(other, self.__class__):
            return NotImplemented
        return self.value == other.value

    def __hash__(self) -> int:
        """Return hash for use in sets and dicts."""
        return hash((self.__class__, self.value))


class DateValueObject(RootModel[date], ValueObject):
    """Base class for Value Objects wrapping a date value."""

    model_config: ClassVar[ConfigDict] = ConfigDict(
        frozen=True,
        extra=None,
    )

    root: date

    def __init__(self, root: Any = None, /, **data: Any) -> None:
        try:
            if root is not None:
                RootModel.__init__(self, root)
            else:
                RootModel.__init__(self, **data)
        except ValidationError as e:
            raise DomainValidationException.from_pydantic_errors(
                object_type=self.__class__.__name__,
                pydantic_errors=e.errors(),
            ) from e

    @property
    def value(self) -> date:
        """Return the wrapped date value."""
        return self.root

    def __str__(self) -> str:
        """Return the ISO format string representation of the date."""
        return self.value.isoformat()

    def __repr__(self) -> str:
        """Return a detailed string representation."""
        return f"{self.__class__.__name__}({self.value!r})"

    def __eq__(self, other: object) -> bool:
        """Check equality with another DateValueObject of the same type."""
        if not isinstance(other, self.__class__):
            return NotImplemented
        return self.value == other.value

    def __hash__(self) -> int:
        """Return hash for use in sets and dicts."""
        return hash((self.__class__, self.value))


__all__ = [
    "DateValueObject",
    "FloatValueObject",
    "IntValueObject",
    "StringValueObject",
    "ValueObject",
]
