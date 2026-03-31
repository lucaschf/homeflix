"""Domain building block errors.

This module combines the base exception classes and domain-specific exceptions
into a single module for the building_blocks package.

Provides:
- CoreException: Base for all application exceptions
- ExceptionDetail / Severity: Supporting types
- DomainException hierarchy: Domain layer error types

See exception-hierarchy-clean-architecture.md for full documentation.
"""

import uuid
from dataclasses import dataclass, replace
from dataclasses import field as dataclass_field
from datetime import UTC, datetime
from enum import Enum
from typing import Any


class Severity(str, Enum):
    """Severity levels for observability and alerting.

    Used to determine log level and alert priority.
    """

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class ExceptionDetail:
    """Structured error detail for composite errors.

    Used for validation errors with multiple fields, where each field
    can have its own error message.

    Attributes:
        code: Error code (e.g., "FIELD_INVALID", "REQUIRED_FIELD")
        message: Human-readable error message (translated)
        field: Related field name (optional)
        metadata: Additional context data (optional)
    """

    code: str
    message: str
    field: str | None = None
    metadata: dict[str, Any] = dataclass_field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary, excluding None values."""
        result: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.field is not None:
            result["field"] = self.field
        if self.metadata:
            result["metadata"] = self.metadata
        return result


@dataclass
class CoreException(Exception):
    """Base exception for all application exceptions.

    Provides:
    - Standardized, serializable structure
    - Traceability via exception_id
    - Observability support via severity and tags
    - i18n support via message_code

    Attributes:
        message: Human-readable error message (can be translated)
        code: Unique error type code (e.g., "DOMAIN_VALIDATION_ERROR")
        message_code: i18n message key for translation lookup
        message_params: Parameters for message interpolation
        details: List of detailed errors for composite errors
        exception_id: Unique UUID for tracing
        timestamp: When the exception was created
        severity: Severity level for alerting
        tags: Metadata for observability (not sent to client)

    Example:
        >>> raise CoreException(
        ...     message="Something went wrong",
        ...     code="GENERIC_ERROR",
        ...     message_code="INTERNAL_ERROR",
        ...     severity=Severity.HIGH,
        ...     tags={"user_id": "123"}
        ... )
    """

    message: str
    code: str = "CORE_ERROR"
    message_code: str | None = None  # i18n key
    message_params: dict[str, Any] = dataclass_field(default_factory=dict)
    details: list[ExceptionDetail] = dataclass_field(default_factory=list)
    exception_id: str = dataclass_field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = dataclass_field(default_factory=lambda: datetime.now(UTC))
    severity: Severity = Severity.MEDIUM
    tags: dict[str, Any] = dataclass_field(default_factory=dict)

    def __post_init__(self) -> None:
        """Initialize the base Exception with the message."""
        super().__init__(self.message)

        # Default message_code to code if not provided
        if self.message_code is None:
            self.message_code = self.code

    @property
    def http_status(self) -> int:
        """HTTP status code for this error.

        Override in subclasses to map to appropriate status.
        Default is 500 (Internal Server Error).
        """
        return 500

    def to_dict(self, include_internal: bool = False) -> dict[str, Any]:
        """Serialize exception to API response format.

        Follows the API Response Standard REST v3.0 error format.

        Args:
            include_internal: If True, include sensitive data.
                              Use ONLY for logs, NEVER for HTTP response.

        Returns:
            Dictionary with standardized error structure.

        Example output:
            {
                "type": "validation_error",
                "message": "Validation failed",
                "code": "DOMAIN_VALIDATION_ERROR",
                "details": [{"code": "...", "message": "...", "field": "..."}]
            }
        """
        # Base error structure (v3.0 flat format)
        result: dict[str, Any] = {
            "type": self._get_error_type(),
            "message": self.message,
            "code": self.code,
        }

        # Add details if present
        if self.details:
            result["details"] = [d.to_dict() for d in self.details]

        # Internal data for logging only
        if include_internal:
            result["_internal"] = {
                "exception_id": self.exception_id,
                "severity": self.severity.value,
                "tags": self.tags,
                "timestamp": self.timestamp.isoformat(),
                "message_code": self.message_code,
                "message_params": self.message_params,
            }
            if self.__cause__:
                result["_internal"]["cause"] = str(self.__cause__)
                result["_internal"]["cause_type"] = type(self.__cause__).__name__

        return result

    def _get_error_type(self) -> str:
        """Get the error type for API response.

        Maps to standard error types like 'validation_error',
        'not_found_error', etc.
        """
        # Default mapping based on http_status
        status_to_type = {
            400: "invalid_request_error",
            401: "authentication_error",
            403: "permission_error",
            404: "not_found_error",
            409: "conflict_error",
            422: "validation_error",
            429: "rate_limit_error",
            500: "api_error",
            502: "bad_gateway_error",
            503: "service_unavailable_error",
            504: "gateway_timeout_error",
        }
        return status_to_type.get(self.http_status, "api_error")

    def with_translation(self, translated_message: str) -> "CoreException":
        """Create a copy with translated message.

        Used by the i18n middleware/handler to translate messages
        before sending to the client.

        Args:
            translated_message: The translated message

        Returns:
            New exception instance with translated message
        """
        # Create a shallow copy with new message
        return replace(self, message=translated_message)

    def add_detail(
        self,
        code: str,
        message: str,
        field: str | None = None,
        **metadata: Any,
    ) -> "CoreException":
        """Add a detail to this exception (fluent interface).

        Args:
            code: Error code
            message: Error message
            field: Related field name
            **metadata: Additional context

        Returns:
            Self for chaining
        """
        self.details.append(
            ExceptionDetail(
                code=code,
                message=message,
                field=field,
                metadata=metadata or {},
            )
        )
        return self


# =============================================================================
# Domain Exceptions
# =============================================================================


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
    "CoreException",
    "DomainConflictException",
    "DomainException",
    "DomainNotFoundException",
    "DomainValidationException",
    "ExceptionDetail",
    "Severity",
]
