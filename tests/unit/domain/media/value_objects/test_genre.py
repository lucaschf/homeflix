"""Tests for Genre value object."""

import pytest

from src.domain.shared.exceptions.domain import DomainValidationException


class TestGenreCreation:
    """Tests for Genre instantiation."""

    def test_should_create_with_valid_genre(self):
        from src.domain.media.value_objects import Genre

        genre = Genre("Action")

        assert genre.value == "Action"

    def test_should_strip_whitespace(self):
        from src.domain.media.value_objects import Genre

        genre = Genre("  Action  ")

        assert genre.value == "Action"

    def test_should_raise_error_for_empty_string(self):
        from src.domain.media.value_objects import Genre

        with pytest.raises(DomainValidationException, match="cannot be empty"):
            Genre("")

    def test_should_raise_error_for_whitespace_only(self):
        from src.domain.media.value_objects import Genre

        with pytest.raises(DomainValidationException, match="cannot be empty"):
            Genre("   ")

    def test_should_raise_error_when_exceeds_max_length(self):
        from src.domain.media.value_objects import Genre

        long_genre = "A" * 51

        with pytest.raises(DomainValidationException, match="50"):
            Genre(long_genre)

    def test_should_accept_genre_at_max_length(self):
        from src.domain.media.value_objects import Genre

        max_genre = "A" * 50

        genre = Genre(max_genre)

        assert len(genre.value) == 50

    def test_should_raise_error_for_non_string_input(self):
        from src.domain.media.value_objects import Genre

        with pytest.raises(DomainValidationException):
            Genre(123)


class TestGenreEquality:
    """Tests for Genre equality and hashing."""

    def test_should_be_equal_when_same_value(self):
        from src.domain.media.value_objects import Genre

        genre1 = Genre("Action")
        genre2 = Genre("Action")

        assert genre1 == genre2

    def test_should_not_be_equal_when_different_value(self):
        from src.domain.media.value_objects import Genre

        genre1 = Genre("Action")
        genre2 = Genre("Comedy")

        assert genre1 != genre2

    def test_should_be_hashable(self):
        from src.domain.media.value_objects import Genre

        genre = Genre("Action")

        genre_set = {genre}

        assert genre in genre_set

    def test_should_have_same_hash_when_equal(self):
        from src.domain.media.value_objects import Genre

        genre1 = Genre("Action")
        genre2 = Genre("Action")

        assert hash(genre1) == hash(genre2)


class TestGenreStringRepresentation:
    """Tests for Genre string conversion."""

    def test_should_convert_to_string(self):
        from src.domain.media.value_objects import Genre

        genre = Genre("Action")

        assert str(genre) == "Action"

    def test_should_have_descriptive_repr(self):
        from src.domain.media.value_objects import Genre

        genre = Genre("Action")

        assert repr(genre) == "Genre('Action')"


class TestGenreImmutability:
    """Tests for Genre immutability."""

    def test_should_be_immutable(self):
        from src.domain.media.value_objects import Genre

        genre = Genre("Action")

        with pytest.raises(DomainValidationException):
            genre.root = "Comedy"
