"""Base classes for Value Objects.

Value Objects are immutable objects identified by their value, not identity.
"""

from datetime import date
from typing import Any, ClassVar

from pydantic import ConfigDict, RootModel, ValidationError

from src.domain.shared.models.domain_model import DomainModel, _raise_domain_validation


class ValueObject(DomainModel):
    """Base class for composite Value Objects (multiple fields).

    Value Objects MUST be immutable (frozen=True).
    For single-value wrappers, use StringValueObject, IntValueObject, etc.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(
        frozen=True,
        validate_assignment=True,
        extra="forbid",
    )


class StringValueObject(RootModel[str]):
    """Base class for Value Objects wrapping a single string value."""

    model_config: ClassVar[ConfigDict] = ConfigDict(
        frozen=True,
        str_strip_whitespace=True,
    )

    root: str

    def __init__(self, root: Any = None, /, **data: Any) -> None:
        try:
            if root is not None:
                super().__init__(root)
            else:
                super().__init__(**data)
        except ValidationError as e:
            _raise_domain_validation(e, self.__class__.__name__)

    def __setattr__(self, name: str, value: Any) -> None:
        try:
            super().__setattr__(name, value)
        except ValidationError as e:
            _raise_domain_validation(e, self.__class__.__name__)

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


class IntValueObject(RootModel[int]):
    """Base class for Value Objects wrapping a single integer value."""

    model_config: ClassVar[ConfigDict] = ConfigDict(
        frozen=True,
    )

    root: int

    def __init__(self, root: Any = None, /, **data: Any) -> None:
        try:
            if root is not None:
                super().__init__(root)
            else:
                super().__init__(**data)
        except ValidationError as e:
            _raise_domain_validation(e, self.__class__.__name__)

    def __setattr__(self, name: str, value: Any) -> None:
        try:
            super().__setattr__(name, value)
        except ValidationError as e:
            _raise_domain_validation(e, self.__class__.__name__)

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


class FloatValueObject(RootModel[float]):
    """Base class for Value Objects wrapping a single float value."""

    model_config: ClassVar[ConfigDict] = ConfigDict(
        frozen=True,
    )

    root: float

    def __init__(self, root: Any = None, /, **data: Any) -> None:
        try:
            if root is not None:
                super().__init__(root)
            else:
                super().__init__(**data)
        except ValidationError as e:
            _raise_domain_validation(e, self.__class__.__name__)

    def __setattr__(self, name: str, value: Any) -> None:
        try:
            super().__setattr__(name, value)
        except ValidationError as e:
            _raise_domain_validation(e, self.__class__.__name__)

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


class DateValueObject(RootModel[date]):
    """Base class for Value Objects wrapping a date value."""

    model_config: ClassVar[ConfigDict] = ConfigDict(
        frozen=True,
    )

    root: date

    def __init__(self, root: Any = None, /, **data: Any) -> None:
        try:
            if root is not None:
                super().__init__(root)
            else:
                super().__init__(**data)
        except ValidationError as e:
            _raise_domain_validation(e, self.__class__.__name__)

    def __setattr__(self, name: str, value: Any) -> None:
        try:
            super().__setattr__(name, value)
        except ValidationError as e:
            _raise_domain_validation(e, self.__class__.__name__)

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
