"""Domain layer exceptions.

These exceptions represent violations of business rules and domain invariants.
They are raised by entities, value objects, aggregates, and domain services.

See exception-hierarchy-clean-architecture.md for full documentation.
"""

from dataclasses import dataclass
from typing import Any

from src.domain.shared.exceptions.base import (
    CoreException,
    ExceptionDetail,
    Severity,
)


@dataclass
class DomainException(CoreException):
    """Base exception for all domain layer errors.

    Use for errors that represent violations of domain rules,
    regardless of how the application was invoked (API, CLI, event).

    Default HTTP status: 422 (Unprocessable Entity)
    """

    code: str = "DOMAIN_ERROR"
    severity: Severity = Severity.MEDIUM

    @property
    def http_status(self) -> int:
        """Return HTTP status code 422 (Unprocessable Entity)."""
        return 422


@dataclass
class DomainValidationException(DomainException):
    """Invalid state for a domain object (Entity, Value Object, Aggregate).

    Different from UseCaseValidationException:
    - DomainValidation: domain object cannot exist in this state
    - UseCaseValidation: request input is malformed

    Attributes:
        object_type: Type of object being validated (e.g., "CPF", "Movie", "Duration")

    Example:
        >>> raise DomainValidationException(
        ...     message="Invalid CPF",
        ...     message_code="INVALID_CPF",
        ...     object_type="CPF"
        ... )

        >>> # Or with multiple violations:
        >>> raise DomainValidationException.from_violations(
        ...     object_type="Movie",
        ...     violations={
        ...         "title": ("REQUIRED_FIELD", "Title is required"),
        ...         "year": ("INVALID_YEAR", "Year must be between 1888 and 2030")
        ...     }
        ... )
    """

    code: str = "DOMAIN_VALIDATION_ERROR"
    message_code: str = "VALIDATION_FAILED"
    object_type: str = ""

    def __post_init__(self) -> None:
        """Initialize and add object_type to tags if set."""
        super().__post_init__()
        if self.object_type:
            self.tags["object_type"] = self.object_type

    @classmethod
    def from_violations(
        cls,
        object_type: str,
        violations: dict[str, tuple[str, str]],
        **kwargs: Any,
    ) -> "DomainValidationException":
        """Factory to create exception from multiple violations.

        Args:
            object_type: Name of the type being validated
            violations: Dict of field -> (code, message) tuples
            **kwargs: Additional arguments for the exception

        Returns:
            DomainValidationException with details populated

        Example:
            >>> exc = DomainValidationException.from_violations(
            ...     object_type="Movie",
            ...     violations={
            ...         "year": ("INVALID_YEAR", "Year out of range"),
            ...         "duration": ("NEGATIVE_DURATION", "Duration must be positive"),
            ...     }
            ... )
        """
        details = [
            ExceptionDetail(
                code=code,
                message=msg,
                field=field_name,
            )
            for field_name, (code, msg) in violations.items()
        ]
        return cls(
            message=f"Validation failed for {object_type}",
            message_code="VALIDATION_FAILED_FOR_TYPE",
            message_params={"type": object_type},
            object_type=object_type,
            details=details,
            **kwargs,
        )

    @classmethod
    def from_pydantic_errors(
        cls,
        object_type: str,
        pydantic_errors: list[Any],
        **kwargs: Any,
    ) -> "DomainValidationException":
        """Factory to create exception from Pydantic validation errors.

        Args:
            object_type: Name of the type being validated
            pydantic_errors: List of Pydantic error dicts
            **kwargs: Additional arguments for the exception

        Returns:
            DomainValidationException with details populated
        """
        details = [
            ExceptionDetail(
                code=err.get("type", "VALIDATION_ERROR"),
                message=err.get("msg", "Validation error"),
                field=".".join(str(loc) for loc in err.get("loc", [])),
                metadata={"input": err.get("input")} if "input" in err else {},
            )
            for err in pydantic_errors
        ]

        # Build message including Pydantic error messages for better debugging
        error_messages = [err.get("msg", "Validation error") for err in pydantic_errors]
        combined_message = "; ".join(error_messages) if error_messages else "Validation failed"

        return cls(
            message=combined_message,
            message_code="VALIDATION_FAILED_FOR_TYPE",
            message_params={"type": object_type},
            object_type=object_type,
            details=details,
            **kwargs,
        )

    @classmethod
    def single_field(
        cls,
        object_type: str,
        field: str,
        code: str,
        message: str,
    ) -> "DomainValidationException":
        """Factory for single-field validation error.

        Args:
            object_type: Name of the type being validated
            field: Field name that failed validation
            code: Error code
            message: Error message

        Returns:
            DomainValidationException with single detail
        """
        return cls(
            message=message,
            message_code=code,
            object_type=object_type,
            details=[ExceptionDetail(code=code, message=message, field=field)],
        )


@dataclass
class BusinessRuleViolationException(DomainException):
    """Violation of a business rule.

    Use when an operation violates a domain rule that isn't simply
    data validation.

    Attributes:
        rule_code: Identifier for the violated rule

    Common rule_codes:
    - MEDIA_ALREADY_EXISTS: Media file already in library
    - PROGRESS_EXCEEDS_DURATION: Progress cannot exceed media duration
    - LIST_LIMIT_EXCEEDED: Maximum lists/items reached
    - INVALID_EPISODE_ORDER: Episode number conflict

    Example:
        >>> raise BusinessRuleViolationException(
        ...     message="Media file already exists in library",
        ...     message_code="MEDIA_ALREADY_EXISTS",
        ...     rule_code="MEDIA_ALREADY_EXISTS",
        ...     tags={"file_path": "/movies/inception.mkv"}
        ... )
    """

    code: str = "BUSINESS_RULE_VIOLATION"
    rule_code: str = ""

    def __post_init__(self) -> None:
        """Initialize and add rule_code to tags, using it as message_code if not set."""
        super().__post_init__()
        if self.rule_code:
            self.tags["rule_code"] = self.rule_code
            # Use rule_code as message_code if not set
            if self.message_code == self.code:
                self.message_code = self.rule_code


@dataclass
class DomainNotFoundException(DomainException):
    """Aggregate or Entity not found in the domain.

    Typically raised by repositories or domain services when
    an expected aggregate doesn't exist.

    Attributes:
        resource_type: Type of resource (e.g., "Movie", "Series", "Episode")
        resource_id: Identifier of the resource not found

    Example:
        >>> raise DomainNotFoundException(
        ...     message="Movie not found",
        ...     message_code="MOVIE_NOT_FOUND",
        ...     resource_type="Movie",
        ...     resource_id="mov_2xK9mPqR7nL4"
        ... )
    """

    code: str = "DOMAIN_NOT_FOUND"
    message_code: str = "RESOURCE_NOT_FOUND"
    resource_type: str = ""
    resource_id: str = ""

    @property
    def http_status(self) -> int:
        """Return HTTP status code 404 (Not Found)."""
        return 404

    def __post_init__(self) -> None:
        """Initialize and add resource metadata to tags and message_params."""
        super().__post_init__()
        self.tags["resource_type"] = self.resource_type
        self.tags["resource_id"] = self.resource_id

        # Set message_params for i18n interpolation
        self.message_params = {
            "resource": self.resource_type,
            "id": self.resource_id,
        }

    @classmethod
    def for_entity(
        cls,
        entity_type: str,
        entity_id: str,
    ) -> "DomainNotFoundException":
        """Factory for entity not found.

        Args:
            entity_type: Type of entity (e.g., "Movie", "Episode")
            entity_id: External ID of the entity

        Returns:
            DomainNotFoundException configured for the entity
        """
        return cls(
            message=f"{entity_type} with id '{entity_id}' not found",
            message_code=f"{entity_type.upper()}_NOT_FOUND",
            resource_type=entity_type,
            resource_id=entity_id,
        )


@dataclass
class DomainConflictException(DomainException):
    """Conflict in domain state.

    Use for situations like:
    - Concurrent operations on the same aggregate
    - Attempt to create a resource that already exists
    - Version conflict (optimistic locking)

    Example:
        >>> raise DomainConflictException(
        ...     message="Movie with this file path already exists",
        ...     message_code="DUPLICATE_MEDIA_FILE",
        ...     tags={"file_path": "/movies/inception.mkv"}
        ... )
    """

    code: str = "DOMAIN_CONFLICT"
    message_code: str = "CONFLICT"

    @property
    def http_status(self) -> int:
        """Return HTTP status code 409 (Conflict)."""
        return 409


__all__ = [
    "BusinessRuleViolationException",
    "DomainConflictException",
    "DomainException",
    "DomainNotFoundException",
    "DomainValidationException",
]
