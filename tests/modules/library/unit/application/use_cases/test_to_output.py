"""Tests for the pure ``library_to_output`` mapper."""

import pytest

from src.modules.library.application.use_cases._to_output import library_to_output
from src.modules.library.domain.entities.library import Library


@pytest.mark.unit
class TestLibraryToOutput:
    def test_should_project_counts_as_passed(self) -> None:
        lib = Library.create(name="Movies", library_type="movies", paths=["/m"])

        output = library_to_output(lib, movie_count=42, series_count=7)

        assert output.movie_count == 42
        assert output.series_count == 7

    def test_should_be_deterministic_for_same_inputs(self) -> None:
        lib = Library.create(name="Movies", library_type="movies", paths=["/m"])

        first = library_to_output(lib, movie_count=3, series_count=0)
        second = library_to_output(lib, movie_count=3, series_count=0)

        assert first == second

    def test_should_include_paths_and_name(self) -> None:
        lib = Library.create(
            name="Anime",
            library_type="series",
            paths=["/media/anime", "/media/anime2"],
        )

        output = library_to_output(lib, movie_count=0, series_count=10)

        assert output.name == "Anime"
        assert output.paths == ["/media/anime", "/media/anime2"]
