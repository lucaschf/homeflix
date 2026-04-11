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


@pytest.mark.unit
class TestInfrastructureException:
    """Tests for the base InfrastructureException."""

    def test_should_default_to_http_500(self) -> None:
        exc = InfrastructureException(message="boom")
        assert exc.http_status == 500

    def test_should_have_default_severity_high(self) -> None:
        exc = InfrastructureException(message="boom")
        assert exc.severity == Severity.HIGH

    def test_should_have_default_code(self) -> None:
        exc = InfrastructureException(message="boom")
        assert exc.code == "INFRASTRUCTURE_ERROR"

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
class TestGatewayException:
    """Tests for GatewayException base."""

    def test_should_default_code(self) -> None:
        exc = GatewayException(message="fail")
        assert exc.code == "GATEWAY_ERROR"

    def test_should_add_gateway_name_to_tags(self) -> None:
        exc = GatewayException(message="fail", gateway_name="TMDB")
        assert exc.tags["gateway_name"] == "TMDB"

    def test_should_not_add_empty_gateway_name_to_tags(self) -> None:
        exc = GatewayException(message="fail")
        assert "gateway_name" not in exc.tags

    def test_should_inherit_from_infrastructure_exception(self) -> None:
        exc = GatewayException(message="fail")
        assert isinstance(exc, InfrastructureException)


@pytest.mark.unit
class TestGatewayTimeoutException:
    """Tests for GatewayTimeoutException."""

    def test_should_return_http_504(self) -> None:
        exc = GatewayTimeoutException(message="timeout")
        assert exc.http_status == 504

    def test_should_have_timeout_code(self) -> None:
        exc = GatewayTimeoutException(message="timeout")
        assert exc.code == "GATEWAY_TIMEOUT"

    def test_should_have_service_timeout_message_code(self) -> None:
        exc = GatewayTimeoutException(message="timeout")
        assert exc.message_code == "SERVICE_TIMEOUT"

    def test_should_inherit_from_gateway_exception(self) -> None:
        exc = GatewayTimeoutException(message="timeout")
        assert isinstance(exc, GatewayException)


@pytest.mark.unit
class TestGatewayUnavailableException:
    """Tests for GatewayUnavailableException."""

    def test_should_return_http_503(self) -> None:
        exc = GatewayUnavailableException(message="down")
        assert exc.http_status == 503

    def test_should_have_unavailable_code(self) -> None:
        exc = GatewayUnavailableException(message="down")
        assert exc.code == "GATEWAY_UNAVAILABLE"

    def test_should_have_service_unavailable_message_code(self) -> None:
        exc = GatewayUnavailableException(message="down")
        assert exc.message_code == "SERVICE_UNAVAILABLE"


@pytest.mark.unit
class TestGatewayRateLimitException:
    """Tests for GatewayRateLimitException."""

    def test_should_return_http_429(self) -> None:
        exc = GatewayRateLimitException(message="rate limit")
        assert exc.http_status == 429

    def test_should_have_default_retry_after(self) -> None:
        exc = GatewayRateLimitException(message="rate limit")
        assert exc.retry_after_seconds == 60

    def test_should_accept_custom_retry_after(self) -> None:
        exc = GatewayRateLimitException(message="rate limit", retry_after_seconds=120)
        assert exc.retry_after_seconds == 120

    def test_should_add_retry_after_to_tags(self) -> None:
        exc = GatewayRateLimitException(message="rate limit", retry_after_seconds=30)
        assert exc.tags["retry_after_seconds"] == 30

    def test_should_populate_message_params(self) -> None:
        exc = GatewayRateLimitException(message="rate limit", retry_after_seconds=45)
        assert exc.message_params == {"seconds": 45}

    def test_should_have_rate_limit_code(self) -> None:
        exc = GatewayRateLimitException(message="rate limit")
        assert exc.code == "GATEWAY_RATE_LIMIT"


@pytest.mark.unit
class TestGatewayBadResponseException:
    """Tests for GatewayBadResponseException."""

    def test_should_return_http_502(self) -> None:
        exc = GatewayBadResponseException(message="bad")
        assert exc.http_status == 502

    def test_should_have_bad_response_code(self) -> None:
        exc = GatewayBadResponseException(message="bad")
        assert exc.code == "GATEWAY_BAD_RESPONSE"


@pytest.mark.unit
class TestCircuitOpenException:
    """Tests for CircuitOpenException."""

    def test_should_return_http_503(self) -> None:
        exc = CircuitOpenException(message="circuit open")
        assert exc.http_status == 503

    def test_should_have_default_circuit_timeout(self) -> None:
        exc = CircuitOpenException(message="circuit open")
        assert exc.circuit_timeout == 30

    def test_should_accept_custom_circuit_timeout(self) -> None:
        exc = CircuitOpenException(message="circuit open", circuit_timeout=120)
        assert exc.circuit_timeout == 120

    def test_should_add_circuit_timeout_to_tags(self) -> None:
        exc = CircuitOpenException(message="circuit open", circuit_timeout=90)
        assert exc.tags["circuit_timeout"] == 90

    def test_should_inherit_from_gateway_exception(self) -> None:
        exc = CircuitOpenException(message="circuit open")
        assert isinstance(exc, GatewayException)

    def test_should_have_circuit_open_code(self) -> None:
        exc = CircuitOpenException(message="circuit open")
        assert exc.code == "CIRCUIT_OPEN"


@pytest.mark.unit
class TestRepositoryException:
    """Tests for RepositoryException base."""

    def test_should_inherit_from_infrastructure(self) -> None:
        exc = RepositoryException(message="db error")
        assert isinstance(exc, InfrastructureException)

    def test_should_have_repository_code(self) -> None:
        exc = RepositoryException(message="db error")
        assert exc.code == "REPOSITORY_ERROR"


@pytest.mark.unit
class TestDatabaseConnectionException:
    """Tests for DatabaseConnectionException."""

    def test_should_return_http_503(self) -> None:
        exc = DatabaseConnectionException(message="db down")
        assert exc.http_status == 503

    def test_should_have_critical_severity(self) -> None:
        exc = DatabaseConnectionException(message="db down")
        assert exc.severity == Severity.CRITICAL

    def test_should_have_connection_error_code(self) -> None:
        exc = DatabaseConnectionException(message="db down")
        assert exc.code == "DATABASE_CONNECTION_ERROR"

    def test_should_have_database_unavailable_message_code(self) -> None:
        exc = DatabaseConnectionException(message="db down")
        assert exc.message_code == "DATABASE_UNAVAILABLE"


@pytest.mark.unit
class TestDataIntegrityException:
    """Tests for DataIntegrityException."""

    def test_should_return_http_409(self) -> None:
        exc = DataIntegrityException(message="conflict")
        assert exc.http_status == 409

    def test_should_have_integrity_code(self) -> None:
        exc = DataIntegrityException(message="conflict")
        assert exc.code == "DATA_INTEGRITY_ERROR"

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
class TestFilesystemException:
    """Tests for FilesystemException base."""

    def test_should_have_filesystem_code(self) -> None:
        exc = FilesystemException(message="fs error")
        assert exc.code == "FILESYSTEM_ERROR"

    def test_should_add_path_to_tags(self) -> None:
        exc = FilesystemException(message="fs error", path="/movies/test.mkv")
        assert exc.tags["path"] == "/movies/test.mkv"

    def test_should_not_add_empty_path_to_tags(self) -> None:
        exc = FilesystemException(message="fs error")
        assert "path" not in exc.tags


@pytest.mark.unit
class TestFileNotFoundException:
    """Tests for FileNotFoundException."""

    def test_should_return_http_404(self) -> None:
        exc = FileNotFoundException(message="not found")
        assert exc.http_status == 404

    def test_should_have_file_not_found_code(self) -> None:
        exc = FileNotFoundException(message="not found")
        assert exc.code == "FILE_NOT_FOUND"

    def test_should_have_file_not_found_message_code(self) -> None:
        exc = FileNotFoundException(message="not found")
        assert exc.message_code == "FILE_NOT_FOUND"

    def test_should_inherit_from_filesystem_exception(self) -> None:
        exc = FileNotFoundException(message="not found")
        assert isinstance(exc, FilesystemException)


@pytest.mark.unit
class TestFileAccessException:
    """Tests for FileAccessException."""

    def test_should_return_http_500(self) -> None:
        # Inherits default 500 from InfrastructureException
        exc = FileAccessException(message="denied")
        assert exc.http_status == 500

    def test_should_have_access_error_code(self) -> None:
        exc = FileAccessException(message="denied")
        assert exc.code == "FILE_ACCESS_ERROR"

    def test_should_have_access_denied_message_code(self) -> None:
        exc = FileAccessException(message="denied")
        assert exc.message_code == "FILE_ACCESS_DENIED"

    def test_should_propagate_path_to_tags(self) -> None:
        exc = FileAccessException(
            message="denied",
            path="/movies/secret.mkv",
            internal_message="Permission denied",
        )
        assert exc.tags["path"] == "/movies/secret.mkv"
        assert exc.tags["internal_message"] == "Permission denied"
