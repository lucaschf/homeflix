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

    def test_to_entity_reads_legacy_cast_string_list(self) -> None:
        """Legacy rows stored ``cast`` as ``["Name1", "Name2"]``.

        After the cast-with-photos change the column holds dicts, but
        existing data must still load — entries become ``CastMember``
        with ``profile_path``/``role`` set to ``None``. The next save
        rewrites the row in the new shape.
        """
        movie_id = MovieId.generate()
        now = datetime.now(UTC)
        model = MovieModel(
            external_id=str(movie_id),
            title="Test Movie",
            year=2024,
            duration=7200,
            cast='["Leonardo DiCaprio", "Joseph Gordon-Levitt"]',
            created_at=now,
            updated_at=now,
        )

        entity = MovieMapper.to_entity(model, include_files=False)

        assert len(entity.cast) == 2
        assert entity.cast[0].name == "Leonardo DiCaprio"
        assert entity.cast[0].profile_path is None
        assert entity.cast[0].role is None
        assert entity.cast[1].name == "Joseph Gordon-Levitt"

    def test_to_entity_reads_new_cast_dict_shape(self) -> None:
        """New rows store ``cast`` as ``[{"name", "profile_path", "role"}]``.

        Pin both shapes so a future refactor that drops one of the
        branches in ``_deserialize_cast`` flips a test red.
        """
        movie_id = MovieId.generate()
        now = datetime.now(UTC)
        model = MovieModel(
            external_id=str(movie_id),
            title="Test Movie",
            year=2024,
            duration=7200,
            cast=(
                '[{"name": "Leonardo DiCaprio", "profile_path": '
                '"https://image.tmdb.org/t/p/original/leo.jpg", "role": "Cobb"}]'
            ),
            created_at=now,
            updated_at=now,
        )

        entity = MovieMapper.to_entity(model, include_files=False)

        assert len(entity.cast) == 1
        member = entity.cast[0]
        assert member.name == "Leonardo DiCaprio"
        assert member.profile_path == "https://image.tmdb.org/t/p/original/leo.jpg"
        assert member.role == "Cobb"

    def test_to_entity_collapses_non_list_cast_payload_to_empty(self) -> None:
        """Malformed cast JSON (single object instead of list) → empty cast.

        Defends against a future migration or manual DB edit that
        writes the wrong shape; without the guard, ``for item in items``
        would iterate dict keys and silently produce ``CastMember``s
        named ``"name"``, ``"profile_path"`` etc.
        """
        movie_id = MovieId.generate()
        now = datetime.now(UTC)
        model = MovieModel(
            external_id=str(movie_id),
            title="Test Movie",
            year=2024,
            duration=7200,
            cast='{"name": "Leonardo DiCaprio"}',  # not a list
            created_at=now,
            updated_at=now,
        )

        entity = MovieMapper.to_entity(model, include_files=False)

        assert entity.cast == []

    def test_to_entity_skips_cast_dicts_without_name(self) -> None:
        """Cast entries with empty / missing ``name`` are skipped.

        Keeps the UI from rendering placeholder cards (initials ``?``,
        blank label) when the upstream provider drifts and stops
        sending names.
        """
        movie_id = MovieId.generate()
        now = datetime.now(UTC)
        model = MovieModel(
            external_id=str(movie_id),
            title="Test Movie",
            year=2024,
            duration=7200,
            cast=(
                '[{"name": "Leonardo DiCaprio"}, '
                '{"name": ""}, '
                '{"profile_path": "/foo.jpg"}, '
                '{"name": "   "}]'
            ),
            created_at=now,
            updated_at=now,
        )

        entity = MovieMapper.to_entity(model, include_files=False)

        assert len(entity.cast) == 1
        assert entity.cast[0].name == "Leonardo DiCaprio"
