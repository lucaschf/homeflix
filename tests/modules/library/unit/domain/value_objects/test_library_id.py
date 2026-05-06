"""Tests for LibraryId value object."""

import pytest

from src.building_blocks.domain.errors import DomainValidationException
from src.building_blocks.domain.external_id import RANDOM_PART_LENGTH
from src.modules.library.domain.value_objects.library_id import LibraryId


class TestLibraryIdCreation:
    """Tests for LibraryId instantiation."""

    def test_should_create_with_valid_format(self):
        library_id = LibraryId("lib_abc123abc123")

        assert library_id.value == "lib_abc123abc123"

    def test_should_have_lib_prefix(self):
        library_id = LibraryId("lib_abc123abc123")

        assert library_id.prefix == "lib"

    def test_should_raise_error_for_wrong_prefix(self):
        with pytest.raises(DomainValidationException, match="prefix"):
            LibraryId("mov_abc123abc123")

    def test_should_raise_error_for_invalid_format(self):
        with pytest.raises(DomainValidationException):
            LibraryId("lib_short")


class TestLibraryIdGeneration:
    """Tests for LibraryId.generate()."""

    def test_should_generate_with_lib_prefix(self):
        library_id = LibraryId.generate()

        assert library_id.prefix == "lib"

    def test_should_generate_with_correct_random_part_length(self):
        library_id = LibraryId.generate()

        assert len(library_id.random_part) == RANDOM_PART_LENGTH

    def test_should_generate_unique_ids(self):
        ids = [LibraryId.generate() for _ in range(100)]
        unique_ids = {id_.value for id_ in ids}

        assert len(unique_ids) == 100


class TestLibraryIdEquality:
    """Tests for LibraryId equality."""

    def test_same_library_ids_should_be_equal(self):
        id1 = LibraryId("lib_abc123abc123")
        id2 = LibraryId("lib_abc123abc123")

        assert id1 == id2

    def test_different_library_ids_should_not_be_equal(self):
        id1 = LibraryId("lib_abc123abc123")
        id2 = LibraryId("lib_xyz789xyz789")

        assert id1 != id2

    def test_library_id_should_be_hashable(self):
        library_id = LibraryId("lib_abc123abc123")

        id_set = {library_id}

        assert library_id in id_set
