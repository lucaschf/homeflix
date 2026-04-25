"""Unit tests for MovieMapper."""

from datetime import UTC, datetime

import pytest

from src.modules.media.domain.entities import Movie
from src.modules.media.domain.value_objects import (
    Duration,
    FilePath,
    MediaFile,
    MovieId,
    Resolution,
    Title,
    Year,
)
from src.modules.media.infrastructure.persistence.mappers import MovieMapper
from src.modules.media.infrastructure.persistence.models import MovieModel


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

    def test_to_entity_shallow_returns_empty_files_even_with_legacy_columns(self) -> None:
        """``include_files=False`` must skip the file-loading branch entirely.

        Set the legacy flat columns (``file_path`` etc.) so the default
        path *would* materialize a fallback ``MediaFile``; with the flag
        off, the result is still empty. This pins the search path's
        contract: the use case never reads ``movie.files``, so a
        regression that drops the flag check would re-enable variant
        loading and could re-introduce the lazy-load bug under search.
        """
        movie_id = MovieId.generate()
        now = datetime.now(UTC)
        model = MovieModel(
            external_id=str(movie_id),
            title="Test Movie",
            year=2024,
            duration=7200,
            file_path="/movies/test.mkv",
            file_size=1_000,
            resolution="1080p",
            created_at=now,
            updated_at=now,
        )

        entity = MovieMapper.to_entity(model, include_files=False)

        assert entity.id == movie_id
        assert entity.title.value == "Test Movie"
        assert entity.files == []

    def test_to_entity_default_loads_files_from_legacy_columns(self) -> None:
        """Default ``include_files=True`` still falls back to flat columns.

        Pinned alongside the shallow test so the fallback contract
        doesn't regress silently when someone refactors the flag.
        """
        movie_id = MovieId.generate()
        now = datetime.now(UTC)
        model = MovieModel(
            external_id=str(movie_id),
            title="Test Movie",
            year=2024,
            duration=7200,
            file_path="/movies/test.mkv",
            file_size=1_000,
            resolution="1080p",
            created_at=now,
            updated_at=now,
        )

        entity = MovieMapper.to_entity(model)

        assert len(entity.files) == 1
        assert entity.files[0].file_path.value == "/movies/test.mkv"
