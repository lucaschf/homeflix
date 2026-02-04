"""Tests for LibraryType enumeration."""

from src.domain.library.value_objects.library_type import LibraryType


class TestLibraryType:
    """Tests for LibraryType enum."""

    def test_should_have_movies_type(self):
        assert LibraryType.MOVIES.value == "movies"

    def test_should_have_series_type(self):
        assert LibraryType.SERIES.value == "series"

    def test_should_have_mixed_type(self):
        assert LibraryType.MIXED.value == "mixed"

    def test_should_create_from_string(self):
        lib_type = LibraryType("movies")

        assert lib_type == LibraryType.MOVIES

    def test_should_have_three_types(self):
        assert len(LibraryType) == 3
