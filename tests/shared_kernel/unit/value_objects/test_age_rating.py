"""Tests for AgeRating value object."""

import pytest

from src.building_blocks.domain.errors import DomainValidationException


class TestAgeRatingCreation:
    """Tests for AgeRating instantiation."""

    @pytest.mark.parametrize("age", [0, 7, 10, 12, 14, 16, 17, 18, 21])
    def test_should_create_within_scale(self, age):
        from src.shared_kernel.value_objects import AgeRating

        assert AgeRating(age).value == age

    def test_should_raise_error_for_negative_age(self):
        from src.shared_kernel.value_objects import AgeRating

        with pytest.raises(DomainValidationException, match="negative"):
            AgeRating(-1)

    def test_should_raise_error_above_ceiling(self):
        from src.shared_kernel.value_objects import AgeRating

        with pytest.raises(DomainValidationException, match="21"):
            AgeRating(22)

    def test_should_raise_error_for_non_integer(self):
        from src.shared_kernel.value_objects import AgeRating

        with pytest.raises(DomainValidationException):
            AgeRating("12")  # type: ignore[arg-type]

    def test_should_reject_bool_masquerading_as_int(self):
        from src.shared_kernel.value_objects import AgeRating

        with pytest.raises(DomainValidationException):
            AgeRating(True)  # type: ignore[arg-type]

    def test_should_expose_adult_threshold(self):
        from src.shared_kernel.value_objects import AgeRating

        assert AgeRating.adult().value == 18
        assert AgeRating.ADULT == 18

    @pytest.mark.parametrize("value", [-1, 22])
    def test_should_carry_the_rule_code_on_range_violations(self, value):
        """The code has to survive into the message — that is how it reaches the API."""
        from src.shared_kernel.value_objects import AgeRating

        with pytest.raises(DomainValidationException, match=r"SHARED\.AGE_RATING\.OUT_OF_RANGE"):
            AgeRating(value)


class TestAgeRatingComparison:
    """Ordering comes from IntValueObject and is relied upon by the catalog filter."""

    def test_should_order_by_age(self):
        from src.shared_kernel.value_objects import AgeRating

        assert AgeRating(10) < AgeRating(12)
        assert AgeRating(16) > AgeRating(14)
        assert AgeRating(12) <= AgeRating(12)
        assert AgeRating(18) >= AgeRating(17)

    def test_should_be_equal_when_same_age(self):
        from src.shared_kernel.value_objects import AgeRating

        assert AgeRating(14) == AgeRating(14)
        assert hash(AgeRating(14)) == hash(AgeRating(14))

    def test_should_sort_a_collection(self):
        from src.shared_kernel.value_objects import AgeRating

        ages = [AgeRating(16), AgeRating(0), AgeRating(12)]

        assert [a.value for a in sorted(ages)] == [0, 12, 16]


class TestAgeRatingAllows:
    """The profile-side reading, including the fail-closed rule for unrated content."""

    def test_should_allow_title_below_limit(self):
        from src.shared_kernel.value_objects import AgeRating

        assert AgeRating(14).allows(AgeRating(10)) is True

    def test_should_allow_title_exactly_at_limit(self):
        from src.shared_kernel.value_objects import AgeRating

        assert AgeRating(14).allows(AgeRating(14)) is True

    def test_should_deny_title_above_limit(self):
        from src.shared_kernel.value_objects import AgeRating

        assert AgeRating(14).allows(AgeRating(16)) is False

    @pytest.mark.parametrize("limit", [0, 10, 12, 14, 16, 17])
    def test_should_deny_undetermined_rating_for_any_limit_below_adult(self, limit):
        from src.shared_kernel.value_objects import AgeRating

        assert AgeRating(limit).allows(None) is False

    @pytest.mark.parametrize("limit", [18, 21])
    def test_should_allow_undetermined_rating_from_adult_upwards(self, limit):
        from src.shared_kernel.value_objects import AgeRating

        assert AgeRating(limit).allows(None) is True

    def test_should_not_treat_undetermined_as_suitable_for_everyone(self):
        """The regression this rule exists to prevent: None must never behave like 0."""
        from src.shared_kernel.value_objects import AgeRating

        assert AgeRating(0).allows(None) is False
        assert AgeRating(0).allows(AgeRating(0)) is True
