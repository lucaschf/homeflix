"""Tests for domain layer exceptions."""

from src.building_blocks.domain.errors import (
    BusinessRuleViolationException,
    DomainConflictException,
    DomainException,
    DomainNotFoundException,
    DomainValidationException,
    Severity,
)
from src.building_blocks.presentation.error_mapping import resolve_http_status


class TestDomainException:
    """Tests for DomainException base class."""

    def test_should_have_default_code(self):
        exc = DomainException(message="Domain error")

        assert exc.code == "DOMAIN_ERROR"

    def test_code_should_resolve_to_http_status_422(self):
        # HTTP status lives in the registry now (ADR-012), keyed by code.
        assert resolve_http_status("DOMAIN_ERROR") == 422

    def test_should_have_medium_severity_by_default(self):
        exc = DomainException(message="Domain error")

        assert exc.severity == Severity.MEDIUM


class TestDomainValidationException:
    """Tests for DomainValidationException."""

    def test_should_have_correct_code(self):
        exc = DomainValidationException(message="Validation failed")

        assert exc.code == "DOMAIN_VALIDATION_ERROR"

    def test_should_have_default_message_code(self):
        exc = DomainValidationException(message="Validation failed")

        assert exc.message_code == "VALIDATION_FAILED"

    def test_should_store_object_type(self):
        exc = DomainValidationException(
            message="Invalid movie",
            object_type="Movie",
        )

        assert exc.object_type == "Movie"
        assert exc.tags["object_type"] == "Movie"


class TestDomainValidationExceptionFromViolations:
    """Tests for DomainValidationException.from_violations() factory."""

    def test_should_create_with_multiple_violations(self):
        exc = DomainValidationException.from_violations(
            object_type="Movie",
            violations={
                "title": ("REQUIRED_FIELD", "Title is required"),
                "year": ("INVALID_YEAR", "Year must be between 1888 and 2030"),
            },
        )

        assert exc.object_type == "Movie"
        assert len(exc.details) == 2

    def test_should_set_correct_message(self):
        exc = DomainValidationException.from_violations(
            object_type="Movie",
            violations={"title": ("REQUIRED", "Required")},
        )

        assert "Movie" in exc.message

    def test_should_populate_details_correctly(self):
        exc = DomainValidationException.from_violations(
            object_type="Movie",
            violations={
                "title": ("REQUIRED_FIELD", "Title is required"),
            },
        )

        assert exc.details[0].code == "REQUIRED_FIELD"
        assert exc.details[0].message == "Title is required"
        assert exc.details[0].field == "title"

    def test_should_set_message_params(self):
        exc = DomainValidationException.from_violations(
            object_type="Movie",
            violations={"title": ("REQUIRED", "Required")},
        )

        assert exc.message_params == {"type": "Movie"}


class TestDomainValidationExceptionFromPydanticErrors:
    """Tests for DomainValidationException.from_pydantic_errors() factory."""

    def test_should_create_from_pydantic_error_list(self):
        pydantic_errors = [
            {
                "type": "int_parsing",
                "msg": "Input should be a valid integer",
                "loc": ("age",),
                "input": "not_an_int",
            },
        ]

        exc = DomainValidationException.from_pydantic_errors(
            object_type="User",
            pydantic_errors=pydantic_errors,
        )

        assert exc.object_type == "User"
        assert len(exc.details) == 1
        assert exc.details[0].code == "int_parsing"
        assert exc.details[0].field == "age"

    def test_should_join_nested_loc_with_dots(self):
        pydantic_errors = [
            {
                "type": "error",
                "msg": "Nested error",
                "loc": ("address", "street"),
            },
        ]

        exc = DomainValidationException.from_pydantic_errors(
            object_type="User",
            pydantic_errors=pydantic_errors,
        )

        assert exc.details[0].field == "address.street"

    def test_should_include_input_in_metadata(self):
        pydantic_errors = [
            {
                "type": "error",
                "msg": "Error",
                "loc": ("field",),
                "input": "bad_value",
            },
        ]

        exc = DomainValidationException.from_pydantic_errors(
            object_type="User",
            pydantic_errors=pydantic_errors,
        )

        assert exc.details[0].metadata == {"input": "bad_value"}


class TestDomainValidationExceptionSingleField:
    """Tests for DomainValidationException.single_field() factory."""

    def test_should_create_for_single_field_error(self):
        exc = DomainValidationException.single_field(
            object_type="Email",
            field="value",
            code="INVALID_EMAIL",
            message="Email format is invalid",
        )

        assert exc.object_type == "Email"
        assert exc.message == "Email format is invalid"
        assert exc.message_code == "INVALID_EMAIL"
        assert len(exc.details) == 1
        assert exc.details[0].field == "value"


class TestBusinessRuleViolationException:
    """Tests for BusinessRuleViolationException."""

    def test_should_have_correct_code(self):
        exc = BusinessRuleViolationException(message="Rule violated")

        assert exc.code == "BUSINESS_RULE_VIOLATION"

    def test_should_store_rule_code(self):
        exc = BusinessRuleViolationException(
            message="Media already exists",
            rule_code="MEDIA_ALREADY_EXISTS",
        )

        assert exc.rule_code == "MEDIA_ALREADY_EXISTS"
        assert exc.tags["rule_code"] == "MEDIA_ALREADY_EXISTS"

    def test_should_use_rule_code_as_message_code(self):
        exc = BusinessRuleViolationException(
            message="Rule violated",
            rule_code="MY_RULE",
        )

        assert exc.message_code == "MY_RULE"

    def test_should_not_override_explicit_message_code(self):
        exc = BusinessRuleViolationException(
            message="Rule violated",
            rule_code="MY_RULE",
            message_code="CUSTOM_MESSAGE_CODE",
        )

        assert exc.message_code == "CUSTOM_MESSAGE_CODE"


class TestDomainNotFoundException:
    """Tests for DomainNotFoundException."""

    def test_should_have_correct_code(self):
        exc = DomainNotFoundException(message="Not found")

        assert exc.code == "DOMAIN_NOT_FOUND"

    def test_code_should_resolve_to_http_status_404(self):
        assert resolve_http_status("DOMAIN_NOT_FOUND") == 404

    def test_should_store_resource_info(self):
        exc = DomainNotFoundException(
            message="Movie not found",
            resource_type="Movie",
            resource_id="mov_abc123abc123",
        )

        assert exc.resource_type == "Movie"
        assert exc.resource_id == "mov_abc123abc123"
        assert exc.tags["resource_type"] == "Movie"
        assert exc.tags["resource_id"] == "mov_abc123abc123"

    def test_should_set_message_params(self):
        exc = DomainNotFoundException(
            message="Movie not found",
            resource_type="Movie",
            resource_id="mov_abc123abc123",
        )

        assert exc.message_params == {"resource": "Movie", "id": "mov_abc123abc123"}


class TestDomainNotFoundExceptionForEntity:
    """Tests for DomainNotFoundException.for_entity() factory."""

    def test_should_create_for_entity(self):
        exc = DomainNotFoundException.for_entity(
            entity_type="Movie",
            entity_id="mov_abc123abc123",
        )

        assert exc.resource_type == "Movie"
        assert exc.resource_id == "mov_abc123abc123"
        assert "mov_abc123abc123" in exc.message
        assert exc.message_code == "MOVIE_NOT_FOUND"

    def test_should_format_message_correctly(self):
        exc = DomainNotFoundException.for_entity(
            entity_type="Episode",
            entity_id="epi_xyz789xyz789",
        )

        assert exc.message == "Episode with id 'epi_xyz789xyz789' not found"


class TestDomainConflictException:
    """Tests for DomainConflictException."""

    def test_should_have_correct_code(self):
        exc = DomainConflictException(message="Conflict")

        assert exc.code == "DOMAIN_CONFLICT"

    def test_code_should_resolve_to_http_status_409(self):
        assert resolve_http_status("DOMAIN_CONFLICT") == 409

    def test_should_have_default_message_code(self):
        exc = DomainConflictException(message="Conflict")

        assert exc.message_code == "CONFLICT"

    def test_should_accept_custom_tags(self):
        exc = DomainConflictException(
            message="Duplicate file",
            tags={"file_path": "/movies/inception.mkv"},
        )

        assert exc.tags["file_path"] == "/movies/inception.mkv"
