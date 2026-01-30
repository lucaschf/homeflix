"""Base exception classes for the application.

This module provides the foundation for all exceptions in the application,
following Clean Architecture principles with support for:
- Serialization to API responses
- Traceability via exception_id
- Observability via severity and tags
- Internationalization (i18n)

See exception-hierarchy-clean-architecture.md for full documentation.
"""

import uuid
from dataclasses import dataclass
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
        result = {"code": self.code, "message": self.message}
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
        from dataclasses import replace
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
        self.details.append(ExceptionDetail(
            code=code,
            message=message,
            field=field,
            metadata=metadata or {},
        ))
        return self


__all__ = [
    "Severity",
    "ExceptionDetail",
    "CoreException",
]
