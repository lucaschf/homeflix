"""Tests for SeasonNumber value object."""

import pytest

from src.building_blocks.domain.errors import DomainValidationException


class TestSeasonNumberCreation:
    """Tests for SeasonNumber instantiation."""

    def test_should_create_with_positive_number(self):
        from src.modules.media.domain.value_objects import SeasonNumber

        season = SeasonNumber(1)

        assert season.value == 1

    def test_should_accept_zero_for_specials(self):
        from src.modules.media.domain.value_objects import SeasonNumber

        specials = SeasonNumber(0)

        assert specials.value == 0

    def test_should_raise_error_for_negative_number(self):
        from src.modules.media.domain.value_objects import SeasonNumber

        with pytest.raises(DomainValidationException, match="non-negative"):
            SeasonNumber(-1)

    def test_should_raise_error_for_non_integer(self):
        from src.modules.media.domain.value_objects import SeasonNumber

        with pytest.raises(DomainValidationException):
            SeasonNumber("1")  # type: ignore[arg-type]


class TestSeasonNumberComparison:
    """Tests for SeasonNumber comparison operators."""

    def test_should_compare_equal(self):
        from src.modules.media.domain.value_objects import SeasonNumber

        assert SeasonNumber(1) == SeasonNumber(1)

    def test_should_compare_less_than(self):
        from src.modules.media.domain.value_objects import SeasonNumber

        assert SeasonNumber(1) < SeasonNumber(2)

    def test_should_compare_greater_than(self):
        from src.modules.media.domain.value_objects import SeasonNumber

        assert SeasonNumber(2) > SeasonNumber(1)

    def test_should_be_hashable(self):
        from src.modules.media.domain.value_objects import SeasonNumber

        season = SeasonNumber(3)

        assert season in {season}


class TestSeasonNumberImmutability:
    """Tests for SeasonNumber immutability."""

    def test_should_be_immutable(self):
        from src.modules.media.domain.value_objects import SeasonNumber

        season = SeasonNumber(1)

        with pytest.raises(DomainValidationException):
            season.root = 2  # type: ignore[misc]
