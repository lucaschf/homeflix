"""Tests for Title value object."""

import pytest

from src.domain.shared.exceptions.domain import DomainValidationException


class TestTitleCreation:
    """Tests for Title instantiation."""

    def test_should_create_with_valid_title(self):
        from src.domain.media.value_objects import Title

        title = Title("Inception")

        assert title.value == "Inception"

    def test_should_strip_leading_whitespace(self):
        from src.domain.media.value_objects import Title

        title = Title("   Inception")

        assert title.value == "Inception"

    def test_should_strip_trailing_whitespace(self):
        from src.domain.media.value_objects import Title

        title = Title("Inception   ")

        assert title.value == "Inception"

    def test_should_strip_both_leading_and_trailing_whitespace(self):
        from src.domain.media.value_objects import Title

        title = Title("   Inception   ")

        assert title.value == "Inception"

    def test_should_collapse_multiple_spaces_to_single(self):
        from src.domain.media.value_objects import Title

        title = Title("The    Dark    Knight")

        assert title.value == "The Dark Knight"

    def test_should_handle_tabs_and_newlines(self):
        from src.domain.media.value_objects import Title

        title = Title("The\t\tDark\n\nKnight")

        assert title.value == "The Dark Knight"

    def test_should_raise_error_for_empty_string(self):
        from src.domain.media.value_objects import Title

        with pytest.raises(DomainValidationException, match="cannot be empty"):
            Title("")

    def test_should_raise_error_for_whitespace_only(self):
        from src.domain.media.value_objects import Title

        with pytest.raises(DomainValidationException, match="cannot be empty"):
            Title("   ")

    def test_should_raise_error_when_exceeds_max_length(self):
        from src.domain.media.value_objects import Title

        long_title = "A" * 501

        with pytest.raises(DomainValidationException, match="500"):
            Title(long_title)

    def test_should_accept_title_at_max_length(self):
        from src.domain.media.value_objects import Title

        max_title = "A" * 500

        title = Title(max_title)

        assert len(title.value) == 500

    def test_should_raise_error_for_non_string_input(self):
        from src.domain.media.value_objects import Title

        with pytest.raises(DomainValidationException):
            Title(123)


class TestTitleEquality:
    """Tests for Title equality and hashing."""

    def test_should_be_equal_when_same_value(self):
        from src.domain.media.value_objects import Title

        title1 = Title("Inception")
        title2 = Title("Inception")

        assert title1 == title2

    def test_should_not_be_equal_when_different_value(self):
        from src.domain.media.value_objects import Title

        title1 = Title("Inception")
        title2 = Title("Interstellar")

        assert title1 != title2

    def test_should_be_equal_after_normalization(self):
        from src.domain.media.value_objects import Title

        title1 = Title("The Dark Knight")
        title2 = Title("  The   Dark   Knight  ")

        assert title1 == title2

    def test_should_be_hashable(self):
        from src.domain.media.value_objects import Title

        title = Title("Inception")

        title_set = {title}

        assert title in title_set

    def test_should_have_same_hash_when_equal(self):
        from src.domain.media.value_objects import Title

        title1 = Title("Inception")
        title2 = Title("Inception")

        assert hash(title1) == hash(title2)


class TestTitleStringRepresentation:
    """Tests for Title string conversion."""

    def test_should_convert_to_string(self):
        from src.domain.media.value_objects import Title

        title = Title("Inception")

        assert str(title) == "Inception"

    def test_should_have_descriptive_repr(self):
        from src.domain.media.value_objects import Title

        title = Title("Inception")

        assert repr(title) == "Title('Inception')"


class TestTitleImmutability:
    """Tests for Title immutability."""

    def test_should_be_immutable(self):
        from src.domain.media.value_objects import Title

        title = Title("Inception")

        with pytest.raises(DomainValidationException):
            title.root = "Interstellar"
