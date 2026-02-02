"""Tests for Duration value object."""

import pytest

from src.domain.shared.exceptions.domain import DomainValidationException


class TestDurationCreation:
    """Tests for Duration instantiation."""

    def test_should_create_with_zero_value(self):
        from src.domain.media.value_objects import Duration

        duration = Duration(0)

        assert duration.value == 0

    def test_should_create_with_positive_value(self):
        from src.domain.media.value_objects import Duration

        duration = Duration(7200)  # 2 hours

        assert duration.value == 7200

    def test_should_raise_error_for_negative_value(self):
        from src.domain.media.value_objects import Duration

        with pytest.raises(DomainValidationException, match="non-negative"):
            Duration(-1)

    def test_should_raise_error_for_non_integer_input(self):
        from src.domain.media.value_objects import Duration

        with pytest.raises(DomainValidationException):
            Duration("7200")


class TestDurationProperties:
    """Tests for Duration computed properties."""

    def test_minutes_property_should_return_whole_minutes(self):
        from src.domain.media.value_objects import Duration

        duration = Duration(90)  # 90 seconds = 1 minute

        assert duration.minutes == 1

    def test_minutes_property_should_truncate_partial_minutes(self):
        from src.domain.media.value_objects import Duration

        duration = Duration(89)  # 89 seconds = 1.48 minutes

        assert duration.minutes == 1

    def test_hours_property_should_return_whole_hours(self):
        from src.domain.media.value_objects import Duration

        duration = Duration(7200)  # 7200 seconds = 2 hours

        assert duration.hours == 2

    def test_hours_property_should_truncate_partial_hours(self):
        from src.domain.media.value_objects import Duration

        duration = Duration(5400)  # 5400 seconds = 1.5 hours

        assert duration.hours == 1

    def test_format_hms_should_return_formatted_string(self):
        from src.domain.media.value_objects import Duration

        duration = Duration(3723)  # 1h 2m 3s

        assert duration.format_hms() == "01:02:03"

    def test_format_hms_with_zero_duration(self):
        from src.domain.media.value_objects import Duration

        duration = Duration(0)

        assert duration.format_hms() == "00:00:00"

    def test_format_hms_with_large_duration(self):
        from src.domain.media.value_objects import Duration

        duration = Duration(36000)  # 10 hours

        assert duration.format_hms() == "10:00:00"

    def test_format_hms_with_seconds_only(self):
        from src.domain.media.value_objects import Duration

        duration = Duration(45)  # 45 seconds

        assert duration.format_hms() == "00:00:45"


class TestDurationComparison:
    """Tests for Duration comparison operators."""

    def test_should_compare_less_than(self):
        from src.domain.media.value_objects import Duration

        duration1 = Duration(100)
        duration2 = Duration(200)

        assert duration1 < duration2

    def test_should_compare_greater_than(self):
        from src.domain.media.value_objects import Duration

        duration1 = Duration(200)
        duration2 = Duration(100)

        assert duration1 > duration2

    def test_should_compare_less_than_or_equal(self):
        from src.domain.media.value_objects import Duration

        duration1 = Duration(100)
        duration2 = Duration(100)

        assert duration1 <= duration2

    def test_should_compare_greater_than_or_equal(self):
        from src.domain.media.value_objects import Duration

        duration1 = Duration(100)
        duration2 = Duration(100)

        assert duration1 >= duration2

    def test_comparison_with_wrong_type_returns_not_implemented(self):
        from src.domain.media.value_objects import Duration

        duration = Duration(100)

        assert duration.__lt__(100) == NotImplemented


class TestDurationEquality:
    """Tests for Duration equality and hashing."""

    def test_should_be_equal_when_same_value(self):
        from src.domain.media.value_objects import Duration

        duration1 = Duration(7200)
        duration2 = Duration(7200)

        assert duration1 == duration2

    def test_should_not_be_equal_when_different_value(self):
        from src.domain.media.value_objects import Duration

        duration1 = Duration(7200)
        duration2 = Duration(3600)

        assert duration1 != duration2

    def test_should_be_hashable(self):
        from src.domain.media.value_objects import Duration

        duration = Duration(7200)

        duration_set = {duration}

        assert duration in duration_set

    def test_should_have_same_hash_when_equal(self):
        from src.domain.media.value_objects import Duration

        duration1 = Duration(7200)
        duration2 = Duration(7200)

        assert hash(duration1) == hash(duration2)


class TestDurationStringRepresentation:
    """Tests for Duration string conversion."""

    def test_should_convert_to_string(self):
        from src.domain.media.value_objects import Duration

        duration = Duration(7200)

        assert str(duration) == "7200"

    def test_should_have_descriptive_repr(self):
        from src.domain.media.value_objects import Duration

        duration = Duration(7200)

        assert repr(duration) == "Duration(7200)"


class TestDurationImmutability:
    """Tests for Duration immutability."""

    def test_should_be_immutable(self):
        from src.domain.media.value_objects import Duration

        duration = Duration(7200)

        with pytest.raises(DomainValidationException):
            duration.root = 3600
