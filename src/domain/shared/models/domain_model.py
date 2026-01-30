"""Base model for all domain objects using Pydantic.

See ADR-001 for context and decision details.
"""

from __future__ import annotations

from typing import Any, Self

from pydantic import BaseModel, ConfigDict, ValidationError


class DomainValidationError(Exception):
    """Wrapper for Pydantic validation errors in the domain layer.

    This keeps Pydantic errors encapsulated within the domain,
    not exposing pydantic.ValidationError directly.

    Attributes:
        errors: List of error details from Pydantic.
        message: Human-readable error message.
    """

    def __init__(self, errors: list[dict[str, Any]], message: str = "Validation failed"):
        self.errors = errors
        self.message = message
        super().__init__(message)

    @classmethod
    def from_pydantic(cls, exc: ValidationError) -> DomainValidationError:
        """Create from a Pydantic ValidationError, preserving error details."""
        errors = exc.errors()
        messages = [err.get("msg", "") for err in errors]
        combined_message = "; ".join(messages) if messages else "Validation failed"
        return cls(errors=errors, message=combined_message)

    def __str__(self) -> str:
        """Return the error message."""
        return self.message


class DomainModelMeta(type(BaseModel)):
    """Metaclass that ensures model_config cannot be modified after class definition."""

    def __setattr__(self, key: str, value: Any) -> None:
        if key == "model_config":
            raise AttributeError("The model_config attribute is immutable and cannot be changed.")
        super().__setattr__(key, value)


class DomainModel(BaseModel, metaclass=DomainModelMeta):
    """Base model for domain objects (Value Objects, Entities) using Pydantic.

    Features:
    - Wraps Pydantic ValidationError in DomainValidationError
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
            raise DomainValidationError.from_pydantic(e) from e
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
        **kwargs: Any,
    ) -> Self:
        """Validates input data and creates a new model instance.
        Wraps Pydantic ValidationError in DomainValidationError.
        """
        try:
            return super().model_validate(
                obj,
                strict=strict,
                from_attributes=from_attributes,
                context=context,
            )
        except ValidationError as e:
            raise DomainValidationError.from_pydantic(e) from e

    @classmethod
    def model_validate_json(
        cls,
        json_data: str | bytes | bytearray,
        *,
        strict: bool | None = None,
        context: Any | None = None,
        **kwargs: Any,
    ) -> Self:
        """Validates JSON data and creates a new model instance.
        Wraps Pydantic ValidationError in DomainValidationError.
        """
        try:
            return super().model_validate_json(
                json_data,
                strict=strict,
                context=context,
            )
        except ValidationError as e:
            raise DomainValidationError.from_pydantic(e) from e

    def __setattr__(self, name: str, value: Any) -> None:
        """Wraps attribute setting to convert ValidationError to DomainValidationError."""
        try:
            super().__setattr__(name, value)
        except ValidationError as e:
            raise DomainValidationError.from_pydantic(e) from e

    def with_updates(self, **kwargs: Any) -> Self:
        """Creates a new, fully validated instance by applying updates atomically."""
        current_data = self.model_dump()
        current_data.update(kwargs)

        try:
            return self.__class__.model_validate(current_data)
        except ValidationError as e:
            raise DomainValidationError.from_pydantic(e) from e


__all__ = ["DomainModel", "DomainValidationError"]
