"""Application layer exceptions.

These exceptions represent errors in use case flow, authorization,
and input validation at the application level.

See exception-hierarchy-clean-architecture.md for full documentation.
"""

from dataclasses import dataclass
from typing import Any

from src.building_blocks.domain.errors import (
    CoreException,
    ExceptionDetail,
    Severity,
)


@dataclass
class ApplicationException(CoreException):
    """Base exception for all application layer errors.

    Use for errors related to application flow, not domain rules.

    Default HTTP status: 400 (Bad Request)
    """

    code: str = "APPLICATION_ERROR"
    severity: Severity = Severity.MEDIUM

    @property
    def http_status(self) -> int:
        """Return HTTP status code 400 (Bad Request)."""
        return 400


@dataclass
class UseCaseValidationException(ApplicationException):
    """Invalid use case input.

    Different from DomainValidationException:
    - UseCaseValidation: request input is malformed/invalid
    - DomainValidation: domain object cannot exist in this state

    Example:
        >>> raise UseCaseValidationException.required_field("movie_id")

        >>> raise UseCaseValidationException.from_violations({
        ...     "limit": ("INVALID_RANGE", "Limit must be between 1 and 100"),
        ...     "cursor": ("INVALID_FORMAT", "Invalid cursor format")
        ... })
    """

    code: str = "USE_CASE_VALIDATION_ERROR"
    message_code: str = "INVALID_INPUT"

    @classmethod
    def from_violations(
        cls,
        violations: dict[str, tuple[str, str]],
        **kwargs: Any,
    ) -> "UseCaseValidationException":
        """Factory to create exception from multiple input violations.

        Args:
            violations: Dict of field -> (code, message) tuples
            **kwargs: Additional arguments for the exception

        Returns:
            UseCaseValidationException with details populated
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
            message="Invalid input",
            details=details,
            **kwargs,
        )

    @classmethod
    def required_field(cls, field_name: str) -> "UseCaseValidationException":
        """Factory for missing required field.

        Args:
            field_name: Name of the required field

        Returns:
            UseCaseValidationException for missing field
        """
        return cls(
            message=f"Field '{field_name}' is required",
            message_code="REQUIRED_FIELD",
            message_params={"field": field_name},
            details=[
                ExceptionDetail(
                    code="REQUIRED_FIELD",
                    message="Field is required",
                    field=field_name,
                )
            ],
        )

    @classmethod
    def invalid_format(
        cls,
        field_name: str,
        expected: str,
    ) -> "UseCaseValidationException":
        """Factory for invalid field format.

        Args:
            field_name: Name of the field
            expected: Expected format description

        Returns:
            UseCaseValidationException for invalid format
        """
        return cls(
            message=f"Invalid format for '{field_name}'. Expected: {expected}",
            message_code="INVALID_FORMAT",
            message_params={"field": field_name, "expected": expected},
            details=[
                ExceptionDetail(
                    code="INVALID_FORMAT",
                    message=f"Expected: {expected}",
                    field=field_name,
                )
            ],
        )


@dataclass
class UnauthorizedOperationException(ApplicationException):
    """User is not authenticated.

    Use when the operation requires authentication but the user
    is not authenticated or the token is invalid.

    Example:
        >>> raise UnauthorizedOperationException(
        ...     message="Authentication required",
        ...     message_code="AUTH_REQUIRED"
        ... )
    """

    code: str = "UNAUTHORIZED"
    message_code: str = "UNAUTHORIZED"
    severity: Severity = Severity.LOW

    @property
    def http_status(self) -> int:
        """Return HTTP status code 401 (Unauthorized)."""
        return 401


@dataclass
class ForbiddenOperationException(ApplicationException):
    """User doesn't have permission for the operation.

    Use when the user is authenticated but lacks the required
    permissions for the operation.

    Attributes:
        required_permission: Permission that was required

    Example:
        >>> raise ForbiddenOperationException(
        ...     message="Admin access required",
        ...     message_code="ADMIN_REQUIRED",
        ...     required_permission="admin"
        ... )
    """

    code: str = "FORBIDDEN"
    message_code: str = "FORBIDDEN"
    required_permission: str = ""
    severity: Severity = Severity.LOW

    @property
    def http_status(self) -> int:
        """Return HTTP status code 403 (Forbidden)."""
        return 403

    def __post_init__(self) -> None:
        """Initialize and add required_permission to tags if set."""
        super().__post_init__()
        if self.required_permission:
            self.tags["required_permission"] = self.required_permission


@dataclass
class ResourceNotFoundException(ApplicationException):
    """Resource not found at the application level.

    Use when the use case wants to abstract domain details or
    when the "resource" isn't necessarily an aggregate.

    Note:
        Both DomainNotFoundException and ResourceNotFoundException
        map to HTTP 404. Use ResourceNotFoundException when you want
        to hide domain details or enrich the error at the use case level.

    Attributes:
        resource_type: Type of resource
        resource_id: Identifier of the resource

    Example:
        >>> raise ResourceNotFoundException(
        ...     message="Movie not found",
        ...     message_code="MOVIE_NOT_FOUND",
        ...     resource_type="Movie",
        ...     resource_id="mov_2xK9mPqR7nL4"
        ... )
    """

    code: str = "RESOURCE_NOT_FOUND"
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
        if self.resource_type:
            self.tags["resource_type"] = self.resource_type
        if self.resource_id:
            self.tags["resource_id"] = self.resource_id
        self.message_params = {
            "resource": self.resource_type,
            "id": self.resource_id,
        }

    @classmethod
    def for_resource(
        cls,
        resource_type: str,
        resource_id: str,
    ) -> "ResourceNotFoundException":
        """Factory for resource not found.

        Args:
            resource_type: Type of resource
            resource_id: External ID of the resource

        Returns:
            ResourceNotFoundException configured for the resource
        """
        return cls(
            message=f"{resource_type} with id '{resource_id}' not found",
            message_code=f"{resource_type.upper()}_NOT_FOUND",
            resource_type=resource_type,
            resource_id=resource_id,
        )


__all__ = [
    "ApplicationException",
    "ForbiddenOperationException",
    "ResourceNotFoundException",
    "UnauthorizedOperationException",
    "UseCaseValidationException",
]
