"""Tests for base exception classes."""

from datetime import UTC, datetime

from src.building_blocks.domain.errors import (
    CoreException,
    ExceptionDetail,
    Severity,
)


class TestSeverity:
    """Tests for Severity enum."""

    def test_should_have_low_severity(self):
        assert Severity.LOW.value == "low"

    def test_should_have_medium_severity(self):
        assert Severity.MEDIUM.value == "medium"

    def test_should_have_high_severity(self):
        assert Severity.HIGH.value == "high"

    def test_should_have_critical_severity(self):
        assert Severity.CRITICAL.value == "critical"


class TestExceptionDetail:
    """Tests for ExceptionDetail dataclass."""

    def test_should_create_with_required_fields(self):
        detail = ExceptionDetail(code="ERROR_CODE", message="Error message")

        assert detail.code == "ERROR_CODE"
        assert detail.message == "Error message"
        assert detail.field is None
        assert detail.metadata == {}

    def test_should_create_with_all_fields(self):
        detail = ExceptionDetail(
            code="FIELD_ERROR",
            message="Field is invalid",
            field="email",
            metadata={"expected": "valid email"},
        )

        assert detail.code == "FIELD_ERROR"
        assert detail.message == "Field is invalid"
        assert detail.field == "email"
        assert detail.metadata == {"expected": "valid email"}

    def test_to_dict_should_include_required_fields(self):
        detail = ExceptionDetail(code="ERROR_CODE", message="Error message")

        result = detail.to_dict()

        assert result == {"code": "ERROR_CODE", "message": "Error message"}

    def test_to_dict_should_include_field_when_present(self):
        detail = ExceptionDetail(
            code="FIELD_ERROR",
            message="Field is invalid",
            field="email",
        )

        result = detail.to_dict()

        assert result["field"] == "email"

    def test_to_dict_should_include_metadata_when_present(self):
        detail = ExceptionDetail(
            code="ERROR_CODE",
            message="Error message",
            metadata={"key": "value"},
        )

        result = detail.to_dict()

        assert result["metadata"] == {"key": "value"}

    def test_to_dict_should_exclude_empty_metadata(self):
        detail = ExceptionDetail(
            code="ERROR_CODE",
            message="Error message",
            metadata={},
        )

        result = detail.to_dict()

        assert "metadata" not in result


class TestCoreExceptionCreation:
    """Tests for CoreException instantiation."""

    def test_should_create_with_required_fields(self):
        exc = CoreException(message="Something went wrong")

        assert exc.message == "Something went wrong"
        assert exc.code == "CORE_ERROR"
        assert exc.severity == Severity.MEDIUM

    def test_should_create_with_all_fields(self):
        exc = CoreException(
            message="Something went wrong",
            code="CUSTOM_ERROR",
            message_code="ERROR_KEY",
            message_params={"param": "value"},
            severity=Severity.HIGH,
            tags={"user_id": "123"},
        )

        assert exc.message == "Something went wrong"
        assert exc.code == "CUSTOM_ERROR"
        assert exc.message_code == "ERROR_KEY"
        assert exc.message_params == {"param": "value"}
        assert exc.severity == Severity.HIGH
        assert exc.tags == {"user_id": "123"}

    def test_should_generate_unique_exception_id(self):
        exc1 = CoreException(message="Error 1")
        exc2 = CoreException(message="Error 2")

        assert exc1.exception_id != exc2.exception_id

    def test_should_set_timestamp_automatically(self):
        before = datetime.now(UTC)
        exc = CoreException(message="Error")
        after = datetime.now(UTC)

        assert before <= exc.timestamp <= after

    def test_should_default_message_code_to_code(self):
        exc = CoreException(message="Error", code="MY_ERROR")

        assert exc.message_code == "MY_ERROR"

    def test_should_inherit_from_exception(self):
        exc = CoreException(message="Error")

        assert isinstance(exc, Exception)
        assert str(exc) == "Error"


class TestCoreExceptionToDict:
    """Tests for CoreException.to_dict() method."""

    def test_should_include_basic_error_structure(self):
        exc = CoreException(
            message="Something went wrong",
            code="ERROR_CODE",
        )

        result = exc.to_dict()

        # ``type`` belongs to the v3 envelope and is set by the global
        # exception handler from the registry (ADR-012). ``to_dict`` no
        # longer pre-populates it.
        assert "type" not in result
        assert result["message"] == "Something went wrong"
        assert result["code"] == "ERROR_CODE"

    def test_should_include_details_when_present(self):
        exc = CoreException(
            message="Validation failed",
            details=[ExceptionDetail(code="FIELD_ERROR", message="Invalid field")],
        )

        result = exc.to_dict()

        assert "details" in result
        assert len(result["details"]) == 1
        assert result["details"][0]["code"] == "FIELD_ERROR"

    def test_should_not_include_details_when_empty(self):
        exc = CoreException(message="Error")

        result = exc.to_dict()

        assert "details" not in result

    def test_should_not_include_internal_by_default(self):
        exc = CoreException(
            message="Error",
            tags={"secret": "value"},
        )

        result = exc.to_dict()

        assert "_internal" not in result

    def test_should_include_internal_when_requested(self):
        exc = CoreException(
            message="Error",
            code="ERROR_CODE",
            message_code="ERROR_KEY",
            message_params={"key": "value"},
            severity=Severity.HIGH,
            tags={"user_id": "123"},
        )

        result = exc.to_dict(include_internal=True)

        assert "_internal" in result
        internal = result["_internal"]
        assert internal["exception_id"] == exc.exception_id
        assert internal["severity"] == "high"
        assert internal["tags"] == {"user_id": "123"}
        assert internal["message_code"] == "ERROR_KEY"
        assert internal["message_params"] == {"key": "value"}

    def test_should_include_cause_info_when_present(self):
        cause = ValueError("Original error")
        exc = CoreException(message="Wrapped error")
        exc.__cause__ = cause

        result = exc.to_dict(include_internal=True)

        assert result["_internal"]["cause"] == "Original error"
        assert result["_internal"]["cause_type"] == "ValueError"


class TestCoreExceptionWithTranslation:
    """Tests for CoreException.with_translation() method."""

    def test_should_create_copy_with_translated_message(self):
        original = CoreException(message="Original message", code="ERROR_CODE")

        translated = original.with_translation("Translated message")

        assert translated.message == "Translated message"
        assert translated.code == "ERROR_CODE"
        assert original.message == "Original message"  # Original unchanged

    def test_should_preserve_all_other_fields(self):
        original = CoreException(
            message="Original",
            code="CODE",
            message_code="KEY",
            severity=Severity.HIGH,
            tags={"key": "value"},
        )

        translated = original.with_translation("Translated")

        assert translated.code == "CODE"
        assert translated.message_code == "KEY"
        assert translated.severity == Severity.HIGH
        assert translated.tags == {"key": "value"}
        assert translated.exception_id == original.exception_id


class TestCoreExceptionAddDetail:
    """Tests for CoreException.add_detail() method."""

    def test_should_add_detail_to_exception(self):
        exc = CoreException(message="Error")

        exc.add_detail(code="DETAIL_CODE", message="Detail message")

        assert len(exc.details) == 1
        assert exc.details[0].code == "DETAIL_CODE"
        assert exc.details[0].message == "Detail message"

    def test_should_add_detail_with_field(self):
        exc = CoreException(message="Error")

        exc.add_detail(
            code="FIELD_ERROR",
            message="Field is invalid",
            field="email",
        )

        assert exc.details[0].field == "email"

    def test_should_add_detail_with_metadata(self):
        exc = CoreException(message="Error")

        exc.add_detail(
            code="ERROR",
            message="Error",
            expected="value1",
            actual="value2",
        )

        assert exc.details[0].metadata == {"expected": "value1", "actual": "value2"}

    def test_should_return_self_for_chaining(self):
        exc = CoreException(message="Error")

        result = exc.add_detail(code="CODE1", message="Message 1")

        assert result is exc

    def test_should_support_fluent_chaining(self):
        exc = (
            CoreException(message="Multiple errors")
            .add_detail(code="CODE1", message="Message 1", field="field1")
            .add_detail(code="CODE2", message="Message 2", field="field2")
        )

        assert len(exc.details) == 2
        assert exc.details[0].code == "CODE1"
        assert exc.details[1].code == "CODE2"
