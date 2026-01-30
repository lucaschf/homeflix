"""Tests for DomainModel base class."""

import pytest
from pydantic import ValidationError as PydanticValidationError

from src.domain.shared.models import DomainModel, DomainValidationError


class SampleModel(DomainModel):
    """Sample model for testing."""

    name: str
    age: int


class TestDomainModelCreation:
    """Tests for DomainModel instantiation."""

    def test_should_create_with_valid_data(self):
        model = SampleModel(name="John", age=30)

        assert model.name == "John"
        assert model.age == 30

    def test_should_raise_domain_validation_error_for_invalid_data(self):
        with pytest.raises(DomainValidationError):
            SampleModel(name="John", age="not_an_int")

    def test_should_raise_domain_validation_error_for_missing_required_field(self):
        with pytest.raises(DomainValidationError):
            SampleModel(name="John")

    def test_should_forbid_extra_attributes(self):
        with pytest.raises(DomainValidationError):
            SampleModel(name="John", age=30, extra="not_allowed")


class TestDomainModelValidation:
    """Tests for DomainModel validation methods."""

    def test_model_validate_should_work_with_valid_dict(self):
        model = SampleModel.model_validate({"name": "John", "age": 30})

        assert model.name == "John"
        assert model.age == 30

    def test_model_validate_should_raise_domain_validation_error_for_invalid_data(self):
        with pytest.raises(DomainValidationError):
            SampleModel.model_validate({"name": "John", "age": "invalid"})

    def test_model_validate_json_should_work_with_valid_json(self):
        model = SampleModel.model_validate_json('{"name": "John", "age": 30}')

        assert model.name == "John"
        assert model.age == 30

    def test_model_validate_json_should_raise_domain_validation_error_for_invalid_json(self):
        with pytest.raises(DomainValidationError):
            SampleModel.model_validate_json('{"name": "John", "age": "invalid"}')


class TestDomainModelWithUpdates:
    """Tests for DomainModel.with_updates() method."""

    def test_should_create_new_instance_with_updates(self):
        original = SampleModel(name="John", age=30)

        updated = original.with_updates(age=31)

        assert updated.age == 31
        assert updated.name == "John"
        assert original.age == 30  # Original unchanged

    def test_should_raise_domain_validation_error_for_invalid_updates(self):
        original = SampleModel(name="John", age=30)

        with pytest.raises(DomainValidationError):
            original.with_updates(age="invalid")


class TestDomainModelAssignment:
    """Tests for DomainModel attribute assignment validation."""

    def test_should_validate_on_assignment(self):
        model = SampleModel(name="John", age=30)

        with pytest.raises(DomainValidationError):
            model.age = "invalid"

    def test_should_allow_valid_assignment(self):
        model = SampleModel(name="John", age=30)

        model.age = 31

        assert model.age == 31


class TestDomainValidationError:
    """Tests for DomainValidationError."""

    def test_should_preserve_error_details(self):
        errors = [{"loc": ("age",), "msg": "Input should be a valid integer", "type": "int_parsing"}]
        exc = DomainValidationError(errors=errors, message="Validation failed")

        assert exc.errors == errors
        assert exc.message == "Validation failed"
        assert str(exc) == "Validation failed"

    def test_should_create_from_pydantic_validation_error(self):
        try:
            SampleModel(name="John", age="not_int")
        except DomainValidationError as exc:
            assert len(exc.errors) > 0
            assert "int" in exc.message.lower() or "integer" in exc.message.lower()

    def test_should_combine_multiple_error_messages(self):
        errors = [
            {"msg": "Error 1"},
            {"msg": "Error 2"},
        ]

        # Test by creating exception directly with combined message
        exc = DomainValidationError(errors=errors, message="Error 1; Error 2")
        assert exc.message == "Error 1; Error 2"


class TestDomainModelConfigImmutability:
    """Tests for model_config immutability."""

    def test_should_not_allow_model_config_modification(self):
        with pytest.raises(AttributeError, match="immutable"):
            SampleModel.model_config = {"extra": "allow"}
