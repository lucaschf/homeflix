"""Unit tests for MovieMapper."""

import pytest

from src.domain.media.entities import Movie
from src.domain.media.value_objects import (
    Duration,
    FilePath,
    MediaFile,
    MovieId,
    Resolution,
    Title,
    Year,
)
from src.infrastructure.persistence.mappers import MovieMapper


def _create_movie(movie_id: MovieId | None = None) -> Movie:
    """Create a Movie entity for testing."""
    return Movie(
        id=movie_id,
        title=Title("Test Movie"),
        year=Year(2024),
        duration=Duration(7200),
        files=[
            MediaFile(
                file_path=FilePath("/movies/test.mkv"),
                file_size=1_000_000_000,
                resolution=Resolution("1080p"),
                is_primary=True,
            )
        ],
    )


@pytest.mark.unit
class TestMovieMapper:
    """Unit tests for MovieMapper."""

    def test_to_model_raises_when_id_is_none(self) -> None:
        """Test that to_model raises ValueError when entity has no ID."""
        movie = _create_movie(movie_id=None)

        with pytest.raises(ValueError, match="Cannot map entity without ID"):
            MovieMapper.to_model(movie)

    def test_to_model_converts_entity_correctly(self) -> None:
        """Test that to_model converts all fields correctly."""
        movie_id = MovieId.generate()
        movie = _create_movie(movie_id=movie_id)

        model = MovieMapper.to_model(movie)

        assert model.external_id == str(movie_id)
        assert model.title == "Test Movie"
        assert model.year == 2024
        assert model.duration == 7200
