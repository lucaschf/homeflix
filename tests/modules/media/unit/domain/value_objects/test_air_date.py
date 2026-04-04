"""Tests for AirDate value object."""

from datetime import date, timedelta

import pytest

from src.building_blocks.domain.errors import DomainValidationException


class TestAirDateCreation:
    """Tests for AirDate instantiation."""

    def test_should_create_with_valid_date(self):
        from src.modules.media.domain.value_objects import AirDate

        air_date = AirDate(date(2024, 1, 15))

        assert air_date.value == date(2024, 1, 15)

    def test_should_create_with_minimum_valid_date(self):
        from src.modules.media.domain.value_objects import AirDate

        air_date = AirDate(date(1800, 1, 1))

        assert air_date.value == date(1800, 1, 1)

    def test_should_create_with_today(self):
        from src.modules.media.domain.value_objects import AirDate

        today = date.today()
        air_date = AirDate(today)

        assert air_date.value == today

    def test_should_create_with_future_date_within_limit(self):
        from src.modules.media.domain.value_objects import AirDate

        future_date = date.today() + timedelta(days=365)
        air_date = AirDate(future_date)

        assert air_date.value == future_date

    def test_should_create_with_upper_boundary_date(self):
        from src.modules.media.domain.value_objects.air_date import AirDate

        upper_boundary = date.today() + timedelta(days=AirDate.MAX_YEARS_AHEAD * 365)
        air_date = AirDate(upper_boundary)

        assert air_date.value == upper_boundary

    def test_should_raise_error_for_date_before_minimum(self):
        from src.modules.media.domain.value_objects import AirDate

        with pytest.raises(DomainValidationException, match="1800"):
            AirDate(date(1799, 12, 31))

    def test_should_raise_error_for_date_too_far_in_future(self):
        from src.modules.media.domain.value_objects import AirDate

        far_future = date.today() + timedelta(days=3 * 365)

        with pytest.raises(DomainValidationException, match="Air date"):
            AirDate(far_future)


class TestAirDateBehavior:
    """Tests for AirDate value object behavior."""

    def test_str_should_return_iso_format(self):
        from src.modules.media.domain.value_objects import AirDate

        air_date = AirDate(date(2024, 1, 15))

        assert str(air_date) == "2024-01-15"

    def test_should_be_equal_when_same_date(self):
        from src.modules.media.domain.value_objects import AirDate

        date1 = AirDate(date(2024, 1, 15))
        date2 = AirDate(date(2024, 1, 15))

        assert date1 == date2

    def test_should_not_be_equal_when_different_date(self):
        from src.modules.media.domain.value_objects import AirDate

        date1 = AirDate(date(2024, 1, 15))
        date2 = AirDate(date(2024, 1, 16))

        assert date1 != date2

    def test_should_be_hashable(self):
        from src.modules.media.domain.value_objects import AirDate

        air_date = AirDate(date(2024, 1, 15))

        assert hash(air_date) == hash(AirDate(date(2024, 1, 15)))

    def test_should_be_usable_in_set(self):
        from src.modules.media.domain.value_objects import AirDate

        dates = {AirDate(date(2024, 1, 15)), AirDate(date(2024, 1, 15))}

        assert len(dates) == 1
