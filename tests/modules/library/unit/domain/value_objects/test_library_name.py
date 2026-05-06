"""Tests for LibraryName value object."""

import pytest

from src.building_blocks.domain.errors import DomainValidationException
from src.modules.library.domain.value_objects.library_name import LibraryName


class TestLibraryNameCreation:
    """Tests for LibraryName instantiation."""

    def test_should_create_with_valid_name(self):
        name = LibraryName("My Movies")

        assert name.value == "My Movies"

    def test_should_trim_whitespace(self):
        name = LibraryName("  Anime Collection  ")

        assert name.value == "Anime Collection"

    def test_should_accept_single_character(self):
        name = LibraryName("A")

        assert name.value == "A"

    def test_should_accept_max_length_name(self):
        long_name = "A" * 100

        name = LibraryName(long_name)

        assert len(name.value) == 100


class TestLibraryNameValidation:
    """Tests for LibraryName validation."""

    def test_should_raise_error_for_empty_string(self):
        with pytest.raises(DomainValidationException, match="cannot be empty"):
            LibraryName("")

    def test_should_raise_error_for_whitespace_only(self):
        with pytest.raises(DomainValidationException, match="cannot be empty"):
            LibraryName("   ")

    def test_should_raise_error_for_name_exceeding_max_length(self):
        long_name = "A" * 101

        with pytest.raises(DomainValidationException, match="cannot exceed 100"):
            LibraryName(long_name)


class TestLibraryNameEquality:
    """Tests for LibraryName equality."""

    def test_same_names_should_be_equal(self):
        name1 = LibraryName("My Movies")
        name2 = LibraryName("My Movies")

        assert name1 == name2

    def test_different_names_should_not_be_equal(self):
        name1 = LibraryName("Movies")
        name2 = LibraryName("Series")

        assert name1 != name2

    def test_should_be_hashable(self):
        name = LibraryName("My Movies")

        name_set = {name}

        assert name in name_set
