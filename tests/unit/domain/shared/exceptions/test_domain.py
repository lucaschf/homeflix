"""Tests for domain layer exceptions."""

from src.domain.shared.exceptions.base import Severity
from src.domain.shared.exceptions.domain import (
    BusinessRuleViolationException,
    DomainConflictException,
    DomainException,
    DomainNotFoundException,
    DomainValidationException,
)


class TestDomainException:
    """Tests for DomainException base class."""

    def test_should_have_default_code(self):
        exc = DomainException(message="Domain error")

        assert exc.code == "DOMAIN_ERROR"

    def test_should_have_http_status_422(self):
        exc = DomainException(message="Domain error")

        assert exc.http_status == 422

    def test_should_have_medium_severity_by_default(self):
        exc = DomainException(message="Domain error")

        assert exc.severity == Severity.MEDIUM

    def test_should_map_to_validation_error_type(self):
        exc = DomainException(message="Domain error")

        assert exc._get_error_type() == "validation_error"


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

    def test_should_have_http_status_404(self):
        exc = DomainNotFoundException(message="Not found")

        assert exc.http_status == 404

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

    def test_should_map_to_not_found_error_type(self):
        exc = DomainNotFoundException(message="Not found")

        assert exc._get_error_type() == "not_found_error"


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

    def test_should_have_http_status_409(self):
        exc = DomainConflictException(message="Conflict")

        assert exc.http_status == 409

    def test_should_have_default_message_code(self):
        exc = DomainConflictException(message="Conflict")

        assert exc.message_code == "CONFLICT"

    def test_should_map_to_conflict_error_type(self):
        exc = DomainConflictException(message="Conflict")

        assert exc._get_error_type() == "conflict_error"

    def test_should_accept_custom_tags(self):
        exc = DomainConflictException(
            message="Duplicate file",
            tags={"file_path": "/movies/inception.mkv"},
        )

        assert exc.tags["file_path"] == "/movies/inception.mkv"
