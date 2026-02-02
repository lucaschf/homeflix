"""Base model for all domain objects using Pydantic.

See ADR-001 for context and decision details.
"""

from __future__ import annotations

from typing import Any, NoReturn, Self

from pydantic import BaseModel, ConfigDict, ValidationError

from src.domain.shared.exceptions.domain import DomainValidationException


def _raise_domain_validation(exc: ValidationError, object_type: str) -> NoReturn:
    """Convert Pydantic ValidationError to DomainValidationException.

    Args:
        exc: The Pydantic validation error.
        object_type: Name of the type being validated.

    Raises:
        DomainValidationException: Always raised with converted error details.
    """
    raise DomainValidationException.from_pydantic_errors(
        object_type=object_type,
        pydantic_errors=exc.errors(),
    ) from exc


class DomainModelMeta(type(BaseModel)):
    """Metaclass that ensures model_config cannot be modified after class definition."""

    def __setattr__(self, key: str, value: Any) -> None:
        if key == "model_config":
            raise AttributeError("The model_config attribute is immutable and cannot be changed.")
        super().__setattr__(key, value)


class DomainModel(BaseModel, metaclass=DomainModelMeta):
    """Base model for domain objects (Value Objects, Entities) using Pydantic.

    Features:
    - Wraps Pydantic ValidationError in DomainValidationException
    - Enforces strict configuration (extra='forbid', validate_assignment=True)
    - Provides atomic update method for immutable transitions

    See ADR-001 for context and decision details.
    """

    model_config = ConfigDict(
        validate_assignment=True,
        extra="forbid",
    )

    def __init__(self, **data: Any) -> None:
        try:
            super().__init__(**data)
        except ValidationError as e:
            _raise_domain_validation(e, self.__class__.__name__)
        self._ensure_model_config()

    def _ensure_model_config(self) -> None:
        """Validate that required config options are set."""
        if self.model_config.get("extra") != "forbid":
            raise ValueError("Domain objects must forbid extra attributes")

        if self.model_config.get("validate_assignment") is not True:
            raise ValueError("Domain objects must validate on assignment")

    @classmethod
    def model_validate(
        cls,
        obj: Any,
        *,
        strict: bool | None = None,
        from_attributes: bool | None = None,
        context: Any | None = None,
    ) -> Self:
        """Validate input data and create a new model instance.

        Wraps Pydantic ValidationError in DomainValidationException.
        """
        try:
            return super().model_validate(
                obj,
                strict=strict,
                from_attributes=from_attributes,
                context=context,
            )
        except ValidationError as e:
            _raise_domain_validation(e, cls.__name__)

    @classmethod
    def model_validate_json(
        cls,
        json_data: str | bytes | bytearray,
        *,
        strict: bool | None = None,
        context: Any | None = None,
    ) -> Self:
        """Validate JSON data and create a new model instance.

        Wraps Pydantic ValidationError in DomainValidationException.
        """
        try:
            return super().model_validate_json(
                json_data,
                strict=strict,
                context=context,
            )
        except ValidationError as e:
            _raise_domain_validation(e, cls.__name__)

    def __setattr__(self, name: str, value: Any) -> None:
        """Wraps attribute setting to convert ValidationError to DomainValidationException."""
        try:
            super().__setattr__(name, value)
        except ValidationError as e:
            _raise_domain_validation(e, self.__class__.__name__)

    def with_updates(self, **kwargs: Any) -> Self:
        """Creates a new, fully validated instance by applying updates atomically."""
        current_data = self.model_dump()
        current_data.update(kwargs)

        try:
            return self.__class__.model_validate(current_data)
        except ValidationError as e:
            _raise_domain_validation(e, self.__class__.__name__)


__all__ = ["DomainModel"]
