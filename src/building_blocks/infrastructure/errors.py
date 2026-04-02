"""Infrastructure layer exceptions.

These exceptions represent errors in communication with external
services, databases, and other infrastructure components.

See exception-hierarchy-clean-architecture.md for full documentation.
"""

from dataclasses import dataclass

from src.building_blocks.domain.errors import (
    CoreException,
    Severity,
)


@dataclass
class InfrastructureException(CoreException):
    """Base exception for all infrastructure layer errors.

    IMPORTANT: These exceptions should NEVER expose internal
    details to the client. Use `internal_message` for logging.

    Attributes:
        internal_message: Technical details for logs only

    Default HTTP status: 500 (Internal Server Error)
    """

    code: str = "INFRASTRUCTURE_ERROR"
    internal_message: str = ""  # For logs only, never exposed
    severity: Severity = Severity.HIGH

    def __post_init__(self) -> None:
        """Initialize and add internal_message to tags if set."""
        super().__post_init__()
        if self.internal_message:
            self.tags["internal_message"] = self.internal_message

    @property
    def http_status(self) -> int:
        """Return HTTP status code 500 (Internal Server Error)."""
        return 500


# =============================================================================
# Gateway Exceptions (External Services)
# =============================================================================


@dataclass
class GatewayException(InfrastructureException):
    """Base for external service (gateway) errors.

    Attributes:
        gateway_name: Name of the external service (e.g., "TMDB", "OMDb")
    """

    code: str = "GATEWAY_ERROR"
    gateway_name: str = ""

    def __post_init__(self) -> None:
        """Initialize and add gateway_name to tags if set."""
        super().__post_init__()
        if self.gateway_name:
            self.tags["gateway_name"] = self.gateway_name


@dataclass
class GatewayTimeoutException(GatewayException):
    """Timeout communicating with external service.

    Example:
        >>> raise GatewayTimeoutException(
        ...     message="External service timed out",
        ...     message_code="SERVICE_TIMEOUT",
        ...     gateway_name="TMDB",
        ...     internal_message="Timeout after 30s connecting to api.themoviedb.org"
        ... )
    """

    code: str = "GATEWAY_TIMEOUT"
    message_code: str = "SERVICE_TIMEOUT"

    @property
    def http_status(self) -> int:
        """Return HTTP status code 504 (Gateway Timeout)."""
        return 504


@dataclass
class GatewayUnavailableException(GatewayException):
    """External service is unavailable.

    Example:
        >>> raise GatewayUnavailableException(
        ...     message="External service unavailable",
        ...     message_code="SERVICE_UNAVAILABLE",
        ...     gateway_name="TMDB",
        ...     internal_message="HTTP 503 from api.themoviedb.org"
        ... )
    """

    code: str = "GATEWAY_UNAVAILABLE"
    message_code: str = "SERVICE_UNAVAILABLE"

    @property
    def http_status(self) -> int:
        """Return HTTP status code 503 (Service Unavailable)."""
        return 503


@dataclass
class GatewayRateLimitException(GatewayException):
    """Rate limited by external service.

    Attributes:
        retry_after_seconds: Suggested retry delay

    Example:
        >>> raise GatewayRateLimitException(
        ...     message="Rate limit exceeded",
        ...     message_code="RATE_LIMIT_EXCEEDED",
        ...     gateway_name="TMDB",
        ...     retry_after_seconds=60
        ... )
    """

    code: str = "GATEWAY_RATE_LIMIT"
    message_code: str = "RATE_LIMIT_EXCEEDED"
    retry_after_seconds: int = 60

    @property
    def http_status(self) -> int:
        """Return HTTP status code 429 (Too Many Requests)."""
        return 429

    def __post_init__(self) -> None:
        """Initialize and add retry_after_seconds to tags and message_params."""
        super().__post_init__()
        self.tags["retry_after_seconds"] = self.retry_after_seconds
        self.message_params = {"seconds": self.retry_after_seconds}


@dataclass
class GatewayBadResponseException(GatewayException):
    """Invalid response from external service.

    Example:
        >>> raise GatewayBadResponseException(
        ...     message="Invalid response from external service",
        ...     message_code="INVALID_GATEWAY_RESPONSE",
        ...     gateway_name="TMDB",
        ...     internal_message="Expected JSON, got HTML: <!DOCTYPE..."
        ... )
    """

    code: str = "GATEWAY_BAD_RESPONSE"
    message_code: str = "INVALID_GATEWAY_RESPONSE"

    @property
    def http_status(self) -> int:
        """Return HTTP status code 502 (Bad Gateway)."""
        return 502


@dataclass
class CircuitOpenException(GatewayException):
    """Circuit breaker is open, requests are being blocked.

    This exception is raised when the circuit breaker has detected
    too many failures and is preventing further requests to protect
    the system from cascading failures.

    Attributes:
        circuit_timeout: Seconds until circuit will attempt to close

    Example:
        >>> raise CircuitOpenException(
        ...     message="Service temporarily unavailable",
        ...     message_code="SERVICE_CIRCUIT_OPEN",
        ...     gateway_name="TMDB",
        ...     circuit_timeout=30
        ... )
    """

    code: str = "CIRCUIT_OPEN"
    message_code: str = "SERVICE_CIRCUIT_OPEN"
    circuit_timeout: int = 30

    @property
    def http_status(self) -> int:
        """Return HTTP status code 503 (Service Unavailable)."""
        return 503

    def __post_init__(self) -> None:
        """Initialize and add circuit_timeout to tags."""
        super().__post_init__()
        self.tags["circuit_timeout"] = self.circuit_timeout


# =============================================================================
# Repository Exceptions (Database)
# =============================================================================


@dataclass
class RepositoryException(InfrastructureException):
    """Base for database/repository errors."""

    code: str = "REPOSITORY_ERROR"


@dataclass
class DatabaseConnectionException(RepositoryException):
    """Failed to connect to database.

    Example:
        >>> raise DatabaseConnectionException(
        ...     message="Database connection failed",
        ...     message_code="DATABASE_UNAVAILABLE",
        ...     internal_message="Connection refused: localhost:5432"
        ... )
    """

    code: str = "DATABASE_CONNECTION_ERROR"
    message_code: str = "DATABASE_UNAVAILABLE"
    severity: Severity = Severity.CRITICAL

    @property
    def http_status(self) -> int:
        """Return HTTP status code 503 (Service Unavailable)."""
        return 503


@dataclass
class DataIntegrityException(RepositoryException):
    """Database constraint violation.

    Attributes:
        constraint_name: Name of the violated constraint (if available)

    Example:
        >>> raise DataIntegrityException(
        ...     message="Data integrity violation",
        ...     message_code="DATA_CONFLICT",
        ...     constraint_name="uq_movies_external_id",
        ...     internal_message="UNIQUE violation on movies.external_id"
        ... )
    """

    code: str = "DATA_INTEGRITY_ERROR"
    message_code: str = "DATA_CONFLICT"
    constraint_name: str = ""

    @property
    def http_status(self) -> int:
        """Return HTTP status code 409 (Conflict)."""
        return 409

    def __post_init__(self) -> None:
        """Initialize and add constraint_name to tags if set."""
        super().__post_init__()
        if self.constraint_name:
            self.tags["constraint_name"] = self.constraint_name


# =============================================================================
# Filesystem Exceptions
# =============================================================================


@dataclass
class FilesystemException(InfrastructureException):
    """Base for filesystem errors.

    Attributes:
        path: Path that caused the error
    """

    code: str = "FILESYSTEM_ERROR"
    path: str = ""

    def __post_init__(self) -> None:
        """Initialize and add path to tags if set."""
        super().__post_init__()
        if self.path:
            self.tags["path"] = self.path


@dataclass
class FileNotFoundException(FilesystemException):
    """File not found on filesystem.

    Example:
        >>> raise FileNotFoundException(
        ...     message="Media file not found",
        ...     message_code="FILE_NOT_FOUND",
        ...     path="/movies/inception.mkv"
        ... )
    """

    code: str = "FILE_NOT_FOUND"
    message_code: str = "FILE_NOT_FOUND"

    @property
    def http_status(self) -> int:
        """Return HTTP status code 404 (Not Found)."""
        return 404


@dataclass
class FileAccessException(FilesystemException):
    """Cannot access file (permission denied, etc.).

    Example:
        >>> raise FileAccessException(
        ...     message="Cannot access media file",
        ...     message_code="FILE_ACCESS_DENIED",
        ...     path="/movies/inception.mkv",
        ...     internal_message="Permission denied: read access"
        ... )
    """

    code: str = "FILE_ACCESS_ERROR"
    message_code: str = "FILE_ACCESS_DENIED"


__all__ = [
    "CircuitOpenException",
    "DataIntegrityException",
    "DatabaseConnectionException",
    "FileAccessException",
    "FileNotFoundException",
    "FilesystemException",
    "GatewayBadResponseException",
    "GatewayException",
    "GatewayRateLimitException",
    "GatewayTimeoutException",
    "GatewayUnavailableException",
    "InfrastructureException",
    "RepositoryException",
]
