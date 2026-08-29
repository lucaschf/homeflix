"""Tests for ContentRating value object."""

import pytest

from src.building_blocks.domain.errors import DomainValidationException


class TestContentRatingCreation:
    """Tests for ContentRating instantiation."""

    def test_should_create_with_valid_rating(self):
        from src.shared_kernel.value_objects import ContentRating

        rating = ContentRating("PG-13")

        assert rating.value == "PG-13"

    def test_should_strip_whitespace(self):
        from src.shared_kernel.value_objects import ContentRating

        rating = ContentRating("  R  ")

        assert rating.value == "R"

    def test_should_raise_error_for_empty_string(self):
        from src.shared_kernel.value_objects import ContentRating

        with pytest.raises(DomainValidationException, match="cannot be empty"):
            ContentRating("")

    def test_should_raise_error_for_whitespace_only(self):
        from src.shared_kernel.value_objects import ContentRating

        with pytest.raises(DomainValidationException, match="cannot be empty"):
            ContentRating("   ")

    def test_should_raise_error_when_exceeds_max_length(self):
        from src.shared_kernel.value_objects import ContentRating

        with pytest.raises(DomainValidationException, match="20"):
            ContentRating("A" * 21)

    def test_should_accept_rating_at_max_length(self):
        from src.shared_kernel.value_objects import ContentRating

        rating = ContentRating("A" * 20)

        assert len(rating.value) == 20

    def test_should_raise_error_for_non_string_input(self):
        from src.shared_kernel.value_objects import ContentRating

        with pytest.raises(DomainValidationException):
            ContentRating(123)  # type: ignore[arg-type]


class TestContentRatingEquality:
    """Tests for ContentRating equality and hashing."""

    def test_should_be_equal_when_same_value(self):
        from src.shared_kernel.value_objects import ContentRating

        assert ContentRating("PG-13") == ContentRating("PG-13")

    def test_should_not_be_equal_when_different_value(self):
        from src.shared_kernel.value_objects import ContentRating

        assert ContentRating("PG-13") != ContentRating("R")

    def test_should_be_hashable(self):
        from src.shared_kernel.value_objects import ContentRating

        rating = ContentRating("R")

        assert rating in {rating}


class TestContentRatingImmutability:
    """Tests for ContentRating immutability."""

    def test_should_be_immutable(self):
        from src.shared_kernel.value_objects import ContentRating

        rating = ContentRating("PG-13")

        with pytest.raises(DomainValidationException):
            rating.root = "R"  # type: ignore[misc]
