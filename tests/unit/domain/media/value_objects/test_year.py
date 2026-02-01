"""Tests for Year value object."""

from datetime import datetime

import pytest

from src.domain.shared.models import DomainValidationError


class TestYearCreation:
    """Tests for Year instantiation."""

    def test_should_create_with_valid_year(self):
        from src.domain.media.value_objects import Year

        year = Year(2024)

        assert year.value == 2024

    def test_should_create_with_minimum_valid_year(self):
        from src.domain.media.value_objects import Year

        year = Year(1800)

        assert year.value == 1800

    def test_should_create_with_future_year_within_limit(self):
        from src.domain.media.value_objects import Year

        current_year = datetime.now().year
        future_year = current_year + 10

        year = Year(future_year)

        assert year.value == future_year

    def test_should_raise_error_for_year_before_minimum(self):
        from src.domain.media.value_objects import Year

        with pytest.raises(DomainValidationError, match="1800"):
            Year(1799)

    def test_should_raise_error_for_year_too_far_in_future(self):
        from src.domain.media.value_objects import Year

        current_year = datetime.now().year
        too_far = current_year + 11

        with pytest.raises(DomainValidationError):
            Year(too_far)

    def test_should_raise_error_for_non_integer_input(self):
        from src.domain.media.value_objects import Year

        with pytest.raises(DomainValidationError):
            Year("2024")


class TestYearComparison:
    """Tests for Year comparison operators."""

    def test_should_compare_less_than(self):
        from src.domain.media.value_objects import Year

        year1 = Year(2020)
        year2 = Year(2024)

        assert year1 < year2

    def test_should_compare_greater_than(self):
        from src.domain.media.value_objects import Year

        year1 = Year(2024)
        year2 = Year(2020)

        assert year1 > year2

    def test_should_compare_less_than_or_equal(self):
        from src.domain.media.value_objects import Year

        year1 = Year(2024)
        year2 = Year(2024)

        assert year1 <= year2

    def test_should_compare_greater_than_or_equal(self):
        from src.domain.media.value_objects import Year

        year1 = Year(2024)
        year2 = Year(2024)

        assert year1 >= year2


class TestYearEquality:
    """Tests for Year equality and hashing."""

    def test_should_be_equal_when_same_value(self):
        from src.domain.media.value_objects import Year

        year1 = Year(2024)
        year2 = Year(2024)

        assert year1 == year2

    def test_should_not_be_equal_when_different_value(self):
        from src.domain.media.value_objects import Year

        year1 = Year(2024)
        year2 = Year(2020)

        assert year1 != year2

    def test_should_be_hashable(self):
        from src.domain.media.value_objects import Year

        year = Year(2024)

        year_set = {year}

        assert year in year_set


class TestYearStringRepresentation:
    """Tests for Year string conversion."""

    def test_should_convert_to_string(self):
        from src.domain.media.value_objects import Year

        year = Year(2024)

        assert str(year) == "2024"

    def test_should_have_descriptive_repr(self):
        from src.domain.media.value_objects import Year

        year = Year(2024)

        assert repr(year) == "Year(2024)"


class TestYearImmutability:
    """Tests for Year immutability."""

    def test_should_be_immutable(self):
        from src.domain.media.value_objects import Year

        year = Year(2024)

        with pytest.raises(DomainValidationError):
            year.root = 2020
