"""Tests for infrastructure exception hierarchy."""

import pytest

from src.building_blocks.domain.errors import Severity
from src.building_blocks.infrastructure.errors import (
    CircuitOpenException,
    DatabaseConnectionException,
    DataIntegrityException,
    FileAccessException,
    FileNotFoundException,
    FilesystemException,
    GatewayBadResponseException,
    GatewayException,
    GatewayRateLimitException,
    GatewayTimeoutException,
    GatewayUnavailableException,
    InfrastructureException,
    RepositoryException,
)

# Exception contract table: (ExceptionClass, http_status, code, message_code)
# Each entry asserts that an instance built with only `message` exposes the
# expected defaults, which catches both accidental overrides and base-class
# regressions in one place.
_EXCEPTION_CONTRACTS = [
    (InfrastructureException, 500, "INFRASTRUCTURE_ERROR", "INFRASTRUCTURE_ERROR"),
    (GatewayException, 500, "GATEWAY_ERROR", "GATEWAY_ERROR"),
    (GatewayTimeoutException, 504, "GATEWAY_TIMEOUT", "SERVICE_TIMEOUT"),
    (GatewayUnavailableException, 503, "GATEWAY_UNAVAILABLE", "SERVICE_UNAVAILABLE"),
    (GatewayRateLimitException, 429, "GATEWAY_RATE_LIMIT", "RATE_LIMIT_EXCEEDED"),
    (GatewayBadResponseException, 502, "GATEWAY_BAD_RESPONSE", "INVALID_GATEWAY_RESPONSE"),
    (CircuitOpenException, 503, "CIRCUIT_OPEN", "SERVICE_CIRCUIT_OPEN"),
    (RepositoryException, 500, "REPOSITORY_ERROR", "REPOSITORY_ERROR"),
    (DatabaseConnectionException, 503, "DATABASE_CONNECTION_ERROR", "DATABASE_UNAVAILABLE"),
    (DataIntegrityException, 409, "DATA_INTEGRITY_ERROR", "DATA_CONFLICT"),
    (FilesystemException, 500, "FILESYSTEM_ERROR", "FILESYSTEM_ERROR"),
    (FileNotFoundException, 404, "FILE_NOT_FOUND", "FILE_NOT_FOUND"),
    (FileAccessException, 500, "FILE_ACCESS_ERROR", "FILE_ACCESS_DENIED"),
]

# Inheritance chain table: (subclass, ancestor)
_INHERITANCE = [
    (GatewayException, InfrastructureException),
    (GatewayTimeoutException, GatewayException),
    (GatewayUnavailableException, GatewayException),
    (GatewayRateLimitException, GatewayException),
    (GatewayBadResponseException, GatewayException),
    (CircuitOpenException, GatewayException),
    (RepositoryException, InfrastructureException),
    (DatabaseConnectionException, RepositoryException),
    (DataIntegrityException, RepositoryException),
    (FilesystemException, InfrastructureException),
    (FileNotFoundException, FilesystemException),
    (FileAccessException, FilesystemException),
]


@pytest.mark.unit
class TestExceptionContracts:
    """Parametrized tests for the exception hierarchy contract."""

    @pytest.mark.parametrize(
        ("exc_class", "expected_status", "_code", "_message_code"),
        _EXCEPTION_CONTRACTS,
        ids=lambda p: p.__name__ if isinstance(p, type) else str(p),
    )
    def test_http_status(
        self,
        exc_class: type[InfrastructureException],
        expected_status: int,
        _code: str,
        _message_code: str,
    ) -> None:
        assert exc_class(message="boom").http_status == expected_status

    @pytest.mark.parametrize(
        ("exc_class", "_status", "expected_code", "_message_code"),
        _EXCEPTION_CONTRACTS,
        ids=lambda p: p.__name__ if isinstance(p, type) else str(p),
    )
    def test_default_code(
        self,
        exc_class: type[InfrastructureException],
        _status: int,
        expected_code: str,
        _message_code: str,
    ) -> None:
        assert exc_class(message="boom").code == expected_code

    @pytest.mark.parametrize(
        ("exc_class", "_status", "_code", "expected_message_code"),
        _EXCEPTION_CONTRACTS,
        ids=lambda p: p.__name__ if isinstance(p, type) else str(p),
    )
    def test_default_message_code(
        self,
        exc_class: type[InfrastructureException],
        _status: int,
        _code: str,
        expected_message_code: str,
    ) -> None:
        assert exc_class(message="boom").message_code == expected_message_code

    @pytest.mark.parametrize(
        ("subclass", "ancestor"),
        _INHERITANCE,
        ids=lambda p: p.__name__ if isinstance(p, type) else str(p),
    )
    def test_inheritance_chain(
        self,
        subclass: type[InfrastructureException],
        ancestor: type[InfrastructureException],
    ) -> None:
        assert issubclass(subclass, ancestor)
        assert isinstance(subclass(message="boom"), ancestor)


@pytest.mark.unit
class TestInfrastructureExceptionBase:
    """Tests for base InfrastructureException features."""

    def test_should_have_default_severity_high(self) -> None:
        assert InfrastructureException(message="boom").severity == Severity.HIGH

    def test_should_add_internal_message_to_tags(self) -> None:
        exc = InfrastructureException(
            message="boom",
            internal_message="Connection refused at 127.0.0.1",
        )
        assert exc.tags["internal_message"] == "Connection refused at 127.0.0.1"

    def test_should_not_add_empty_internal_message_to_tags(self) -> None:
        exc = InfrastructureException(message="boom")
        assert "internal_message" not in exc.tags

    def test_should_be_raisable(self) -> None:
        with pytest.raises(InfrastructureException, match="boom"):
            raise InfrastructureException(message="boom")


@pytest.mark.unit
class TestGatewayExceptionAttributes:
    """Tests for GatewayException attribute-driven tag population."""

    def test_should_add_gateway_name_to_tags(self) -> None:
        exc = GatewayException(message="fail", gateway_name="TMDB")
        assert exc.tags["gateway_name"] == "TMDB"

    def test_should_not_add_empty_gateway_name_to_tags(self) -> None:
        exc = GatewayException(message="fail")
        assert "gateway_name" not in exc.tags


@pytest.mark.unit
class TestGatewayRateLimitAttributes:
    """Tests for GatewayRateLimitException specific attributes."""

    def test_should_have_default_retry_after(self) -> None:
        assert GatewayRateLimitException(message="rate limit").retry_after_seconds == 60

    def test_should_accept_custom_retry_after(self) -> None:
        exc = GatewayRateLimitException(message="rate limit", retry_after_seconds=120)
        assert exc.retry_after_seconds == 120

    def test_should_add_retry_after_to_tags(self) -> None:
        exc = GatewayRateLimitException(message="rate limit", retry_after_seconds=30)
        assert exc.tags["retry_after_seconds"] == 30

    def test_should_populate_message_params(self) -> None:
        exc = GatewayRateLimitException(message="rate limit", retry_after_seconds=45)
        assert exc.message_params == {"seconds": 45}


@pytest.mark.unit
class TestCircuitOpenAttributes:
    """Tests for CircuitOpenException specific attributes."""

    def test_should_have_default_circuit_timeout(self) -> None:
        assert CircuitOpenException(message="circuit open").circuit_timeout == 30

    def test_should_accept_custom_circuit_timeout(self) -> None:
        exc = CircuitOpenException(message="circuit open", circuit_timeout=120)
        assert exc.circuit_timeout == 120

    def test_should_add_circuit_timeout_to_tags(self) -> None:
        exc = CircuitOpenException(message="circuit open", circuit_timeout=90)
        assert exc.tags["circuit_timeout"] == 90


@pytest.mark.unit
class TestDatabaseConnectionAttributes:
    """Tests for DatabaseConnectionException specific attributes."""

    def test_should_have_critical_severity(self) -> None:
        assert DatabaseConnectionException(message="db down").severity == Severity.CRITICAL


@pytest.mark.unit
class TestDataIntegrityAttributes:
    """Tests for DataIntegrityException specific attributes."""

    def test_should_add_constraint_name_to_tags(self) -> None:
        exc = DataIntegrityException(
            message="conflict",
            constraint_name="uq_movies_external_id",
        )
        assert exc.tags["constraint_name"] == "uq_movies_external_id"

    def test_should_not_add_empty_constraint_name_to_tags(self) -> None:
        exc = DataIntegrityException(message="conflict")
        assert "constraint_name" not in exc.tags


@pytest.mark.unit
class TestFilesystemAttributes:
    """Tests for filesystem exception specific attributes."""

    def test_should_add_path_to_tags(self) -> None:
        exc = FilesystemException(message="fs error", path="/movies/test.mkv")
        assert exc.tags["path"] == "/movies/test.mkv"

    def test_should_not_add_empty_path_to_tags(self) -> None:
        exc = FilesystemException(message="fs error")
        assert "path" not in exc.tags

    def test_file_access_should_propagate_path_and_internal_message_to_tags(self) -> None:
        exc = FileAccessException(
            message="denied",
            path="/movies/secret.mkv",
            internal_message="Permission denied",
        )
        assert exc.tags["path"] == "/movies/secret.mkv"
        assert exc.tags["internal_message"] == "Permission denied"
