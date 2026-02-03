"""Tests for DomainModel base class."""

from typing import ClassVar

import pytest

from src.domain.shared.exceptions.domain import DomainValidationException
from src.domain.shared.models import DomainModel


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
        with pytest.raises(DomainValidationException):
            SampleModel(name="John", age="not_an_int")

    def test_should_raise_domain_validation_error_for_missing_required_field(self):
        with pytest.raises(DomainValidationException):
            SampleModel(name="John")

    def test_should_forbid_extra_attributes(self):
        with pytest.raises(DomainValidationException):
            SampleModel(name="John", age=30, extra="not_allowed")


class TestDomainModelValidation:
    """Tests for DomainModel validation methods."""

    def test_model_validate_should_work_with_valid_dict(self):
        model = SampleModel.model_validate({"name": "John", "age": 30})

        assert model.name == "John"
        assert model.age == 30

    def test_model_validate_should_raise_domain_validation_error_for_invalid_data(self):
        with pytest.raises(DomainValidationException):
            SampleModel.model_validate({"name": "John", "age": "invalid"})

    def test_model_validate_json_should_work_with_valid_json(self):
        model = SampleModel.model_validate_json('{"name": "John", "age": 30}')

        assert model.name == "John"
        assert model.age == 30

    def test_model_validate_json_should_raise_domain_validation_error_for_invalid_json(self):
        with pytest.raises(DomainValidationException):
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

        with pytest.raises(DomainValidationException):
            original.with_updates(age="invalid")


class TestDomainModelAssignment:
    """Tests for DomainModel attribute assignment validation."""

    def test_should_validate_on_assignment(self):
        model = SampleModel(name="John", age=30)

        with pytest.raises(DomainValidationException):
            model.age = "invalid"

    def test_should_allow_valid_assignment(self):
        model = SampleModel(name="John", age=30)

        model.age = 31

        assert model.age == 31


class TestDomainValidationException:
    """Tests for DomainValidationException integration with DomainModel."""

    def test_should_preserve_error_details_from_pydantic(self):
        with pytest.raises(DomainValidationException) as exc_info:
            SampleModel(name="John", age="not_int")

        exc = exc_info.value
        assert len(exc.details) > 0
        assert exc.object_type == "SampleModel"

    def test_should_include_pydantic_error_in_message(self):
        with pytest.raises(DomainValidationException) as exc_info:
            SampleModel(name="John", age="not_int")

        exc = exc_info.value
        # Message should contain the Pydantic error message
        assert "integer" in exc.message.lower() or "int" in exc.message.lower()

    def test_should_include_field_in_details(self):
        with pytest.raises(DomainValidationException) as exc_info:
            SampleModel(name="John", age="not_int")

        exc = exc_info.value
        field_names = [detail.field for detail in exc.details]
        assert "age" in field_names


class TestDomainModelConfigValidation:
    """Tests for model_config validation at class definition time."""

    def test_should_reject_subclass_with_invalid_extra_config(self):
        with pytest.raises(TypeError, match="extra='forbid'"):
            # This class definition should fail because extra="allow" is not permitted
            class InvalidExtraModel(DomainModel):
                model_config: ClassVar[dict[str, object]] = {
                    "extra": "allow",
                    "validate_assignment": True,
                }
                name: str

    def test_should_reject_subclass_without_validate_assignment(self):
        with pytest.raises(TypeError, match="validate_assignment=True"):

            class InvalidValidationModel(DomainModel):
                model_config: ClassVar[dict[str, object]] = {
                    "extra": "forbid",
                    "validate_assignment": False,
                }
                name: str
