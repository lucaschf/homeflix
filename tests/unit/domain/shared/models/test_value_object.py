"""Tests for ValueObject base classes."""

from datetime import date

import pytest

from src.domain.shared.models import (
    DateValueObject,
    DomainValidationError,
    FloatValueObject,
    IntValueObject,
    StringValueObject,
    ValueObject,
)


class SampleValueObject(ValueObject):
    """Sample value object for testing."""

    name: str
    code: int


class SampleStringVO(StringValueObject):
    """Sample string value object for testing."""

    pass


class SampleIntVO(IntValueObject):
    """Sample integer value object for testing."""

    pass


class SampleFloatVO(FloatValueObject):
    """Sample float value object for testing."""

    pass


class SampleDateVO(DateValueObject):
    """Sample date value object for testing."""

    pass


class TestValueObjectCreation:
    """Tests for ValueObject instantiation."""

    def test_should_create_with_valid_data(self):
        vo = SampleValueObject(name="Test", code=123)

        assert vo.name == "Test"
        assert vo.code == 123

    def test_should_be_immutable(self):
        vo = SampleValueObject(name="Test", code=123)

        with pytest.raises(Exception):  # ValidationError or similar
            vo.name = "Changed"


class TestStringValueObject:
    """Tests for StringValueObject."""

    def test_should_create_with_string_value(self):
        vo = SampleStringVO("hello")

        assert vo.value == "hello"

    def test_should_strip_whitespace(self):
        vo = SampleStringVO("  hello  ")

        assert vo.value == "hello"

    def test_should_convert_to_string(self):
        vo = SampleStringVO("hello")

        assert str(vo) == "hello"

    def test_should_have_descriptive_repr(self):
        vo = SampleStringVO("hello")

        assert repr(vo) == "SampleStringVO('hello')"

    def test_should_be_equal_when_same_value(self):
        vo1 = SampleStringVO("hello")
        vo2 = SampleStringVO("hello")

        assert vo1 == vo2

    def test_should_not_be_equal_when_different_value(self):
        vo1 = SampleStringVO("hello")
        vo2 = SampleStringVO("world")

        assert vo1 != vo2

    def test_should_be_hashable(self):
        vo = SampleStringVO("hello")

        vo_set = {vo}

        assert vo in vo_set

    def test_should_have_same_hash_when_equal(self):
        vo1 = SampleStringVO("hello")
        vo2 = SampleStringVO("hello")

        assert hash(vo1) == hash(vo2)

    def test_should_return_not_implemented_for_different_types(self):
        vo = SampleStringVO("hello")

        assert vo.__eq__("hello") == NotImplemented

    def test_should_raise_error_for_non_string_input(self):
        with pytest.raises(DomainValidationError):
            SampleStringVO(123)


class TestIntValueObject:
    """Tests for IntValueObject."""

    def test_should_create_with_integer_value(self):
        vo = SampleIntVO(42)

        assert vo.value == 42

    def test_should_convert_to_string(self):
        vo = SampleIntVO(42)

        assert str(vo) == "42"

    def test_should_have_descriptive_repr(self):
        vo = SampleIntVO(42)

        assert repr(vo) == "SampleIntVO(42)"

    def test_should_be_equal_when_same_value(self):
        vo1 = SampleIntVO(42)
        vo2 = SampleIntVO(42)

        assert vo1 == vo2

    def test_should_not_be_equal_when_different_value(self):
        vo1 = SampleIntVO(42)
        vo2 = SampleIntVO(99)

        assert vo1 != vo2

    def test_should_be_hashable(self):
        vo = SampleIntVO(42)

        vo_set = {vo}

        assert vo in vo_set

    def test_should_support_less_than_comparison(self):
        vo1 = SampleIntVO(10)
        vo2 = SampleIntVO(20)

        assert vo1 < vo2
        assert not vo2 < vo1

    def test_should_support_less_than_or_equal_comparison(self):
        vo1 = SampleIntVO(10)
        vo2 = SampleIntVO(10)
        vo3 = SampleIntVO(20)

        assert vo1 <= vo2
        assert vo1 <= vo3
        assert not vo3 <= vo1

    def test_should_support_greater_than_comparison(self):
        vo1 = SampleIntVO(20)
        vo2 = SampleIntVO(10)

        assert vo1 > vo2
        assert not vo2 > vo1

    def test_should_support_greater_than_or_equal_comparison(self):
        vo1 = SampleIntVO(20)
        vo2 = SampleIntVO(20)
        vo3 = SampleIntVO(10)

        assert vo1 >= vo2
        assert vo1 >= vo3
        assert not vo3 >= vo1

    def test_comparison_should_return_not_implemented_for_different_types(self):
        vo = SampleIntVO(42)

        assert vo.__lt__(42) == NotImplemented
        assert vo.__le__(42) == NotImplemented
        assert vo.__gt__(42) == NotImplemented
        assert vo.__ge__(42) == NotImplemented

    def test_should_raise_error_for_non_integer_input(self):
        with pytest.raises(DomainValidationError):
            SampleIntVO("not_an_int")


class TestFloatValueObject:
    """Tests for FloatValueObject."""

    def test_should_create_with_float_value(self):
        vo = SampleFloatVO(3.14)

        assert vo.value == 3.14

    def test_should_convert_to_string(self):
        vo = SampleFloatVO(3.14)

        assert str(vo) == "3.14"

    def test_should_have_descriptive_repr(self):
        vo = SampleFloatVO(3.14)

        assert repr(vo) == "SampleFloatVO(3.14)"

    def test_should_be_equal_when_same_value(self):
        vo1 = SampleFloatVO(3.14)
        vo2 = SampleFloatVO(3.14)

        assert vo1 == vo2

    def test_should_not_be_equal_when_different_value(self):
        vo1 = SampleFloatVO(3.14)
        vo2 = SampleFloatVO(2.71)

        assert vo1 != vo2

    def test_should_be_hashable(self):
        vo = SampleFloatVO(3.14)

        vo_set = {vo}

        assert vo in vo_set

    def test_should_accept_integer_as_float(self):
        vo = SampleFloatVO(42)

        assert vo.value == 42.0

    def test_should_raise_error_for_non_numeric_input(self):
        with pytest.raises(DomainValidationError):
            SampleFloatVO("not_a_float")


class TestDateValueObject:
    """Tests for DateValueObject."""

    def test_should_create_with_date_value(self):
        d = date(2024, 6, 15)
        vo = SampleDateVO(d)

        assert vo.value == d

    def test_should_convert_to_iso_string(self):
        vo = SampleDateVO(date(2024, 6, 15))

        assert str(vo) == "2024-06-15"

    def test_should_have_descriptive_repr(self):
        vo = SampleDateVO(date(2024, 6, 15))

        assert "2024" in repr(vo)
        assert "6" in repr(vo)
        assert "15" in repr(vo)

    def test_should_be_equal_when_same_value(self):
        vo1 = SampleDateVO(date(2024, 6, 15))
        vo2 = SampleDateVO(date(2024, 6, 15))

        assert vo1 == vo2

    def test_should_not_be_equal_when_different_value(self):
        vo1 = SampleDateVO(date(2024, 6, 15))
        vo2 = SampleDateVO(date(2024, 6, 16))

        assert vo1 != vo2

    def test_should_be_hashable(self):
        vo = SampleDateVO(date(2024, 6, 15))

        vo_set = {vo}

        assert vo in vo_set

    def test_should_parse_date_from_string(self):
        vo = SampleDateVO("2024-06-15")

        assert vo.value == date(2024, 6, 15)

    def test_should_raise_error_for_invalid_date_string(self):
        with pytest.raises(DomainValidationError):
            SampleDateVO("not-a-date")
