"""Tests for Movie aggregate root."""

import pytest

from src.building_blocks.domain.errors import DomainValidationException


class TestMovieCreation:
    """Tests for Movie instantiation."""

    def test_should_create_with_required_fields(self):
        from src.modules.media.domain.entities import Movie
        from src.modules.media.domain.value_objects import (
            Duration,
            FilePath,
            MediaFile,
            Resolution,
            Title,
            Year,
        )

        movie = Movie(
            title=Title("Inception"),
            year=Year(2010),
            duration=Duration(8880),
            files=[
                MediaFile(
                    file_path=FilePath("/movies/inception.mkv"),
                    file_size=4_000_000_000,
                    resolution=Resolution("1080p"),
                    is_primary=True,
                )
            ],
        )

        assert movie.id is None
        assert movie.title.value == "Inception"
        assert movie.year.value == 2010

    def test_should_create_via_factory_with_auto_id(self):
        from src.modules.media.domain.entities import Movie
        from src.modules.media.domain.value_objects import MovieId

        movie = Movie.create(
            title="Inception",
            year=2010,
            duration=8880,
            file_path="/movies/inception.mkv",
            file_size=4_000_000_000,
            resolution="1080p",
        )

        assert movie.id is not None
        assert isinstance(movie.id, MovieId)
        assert movie.id.prefix == "mov"

    def test_factory_should_create_primary_file(self):
        from src.modules.media.domain.entities import Movie

        movie = Movie.create(
            title="Inception",
            year=2010,
            duration=8880,
            file_path="/movies/inception.mkv",
            file_size=4_000_000_000,
            resolution="1080p",
        )

        assert len(movie.files) == 1
        assert movie.files[0].is_primary is True
        assert movie.files[0].file_path.value == "/movies/inception.mkv"
        assert movie.files[0].resolution.name == "1080p"

    def test_should_accept_string_id_and_convert(self):
        from src.modules.media.domain.entities import Movie
        from src.modules.media.domain.value_objects import (
            Duration,
            MovieId,
            Title,
            Year,
        )

        movie = Movie(
            id="mov_abc123abc123",
            title=Title("Inception"),
            year=Year(2010),
            duration=Duration(8880),
        )

        assert isinstance(movie.id, MovieId)


class TestMovieOptionalFields:
    """Tests for Movie optional fields."""

    def test_should_create_with_all_optional_fields(self):
        from src.modules.media.domain.entities import Movie
        from src.modules.media.domain.value_objects import (
            Duration,
            FilePath,
            Genre,
            MediaFile,
            Resolution,
            Title,
            Year,
        )

        movie = Movie(
            title=Title("Inception"),
            original_title=Title("Inception"),
            year=Year(2010),
            duration=Duration(8880),
            synopsis="A thief who steals corporate secrets...",
            poster_path=FilePath("/posters/inception.jpg"),
            backdrop_path=FilePath("/backdrops/inception.jpg"),
            genres=[Genre("Sci-Fi"), Genre("Action")],
            files=[
                MediaFile(
                    file_path=FilePath("/movies/inception.mkv"),
                    file_size=4_000_000_000,
                    resolution=Resolution("1080p"),
                    is_primary=True,
                )
            ],
            tmdb_id=27205,
            imdb_id="tt1375666",
        )

        assert movie.original_title is not None
        assert movie.original_title.value == "Inception"
        assert movie.synopsis is not None
        assert len(movie.genres) == 2
        assert movie.tmdb_id == 27205
        assert movie.imdb_id == "tt1375666"


class TestMovieGenreManagement:
    """Tests for Movie genre management."""

    def test_should_add_genre(self):
        from src.modules.media.domain.entities import Movie

        movie = Movie.create(
            title="Inception",
            year=2010,
            duration=8880,
            file_path="/movies/inception.mkv",
            file_size=4_000_000_000,
            resolution="1080p",
        )

        movie = movie.with_genre("Sci-Fi")

        assert len(movie.genres) == 1
        assert movie.genres[0].value == "Sci-Fi"

    def test_should_add_genre_as_value_object(self):
        from src.modules.media.domain.entities import Movie
        from src.modules.media.domain.value_objects import Genre

        movie = Movie.create(
            title="Inception",
            year=2010,
            duration=8880,
            file_path="/movies/inception.mkv",
            file_size=4_000_000_000,
            resolution="1080p",
        )

        movie = movie.with_genre(Genre("Action"))

        assert len(movie.genres) == 1

    def test_should_not_add_duplicate_genre(self):
        from src.modules.media.domain.entities import Movie

        movie = Movie.create(
            title="Inception",
            year=2010,
            duration=8880,
            file_path="/movies/inception.mkv",
            file_size=4_000_000_000,
            resolution="1080p",
        )

        movie = movie.with_genre("Sci-Fi")
        movie = movie.with_genre("Sci-Fi")

        assert len(movie.genres) == 1


class TestMovieFileManagement:
    """Tests for Movie file variant management."""

    def test_primary_file_should_return_primary(self):
        from src.modules.media.domain.entities import Movie

        movie = Movie.create(
            title="Inception",
            year=2010,
            duration=8880,
            file_path="/movies/inception.mkv",
            file_size=4_000_000_000,
            resolution="1080p",
        )

        primary = movie.primary_file
        assert primary is not None
        assert primary.is_primary is True

    def test_primary_file_should_return_none_when_no_files(self):
        from src.modules.media.domain.entities import Movie
        from src.modules.media.domain.value_objects import Duration, Title, Year

        movie = Movie(
            title=Title("Test"),
            year=Year(2024),
            duration=Duration(7200),
        )

        assert movie.primary_file is None

    def test_best_file_should_return_highest_resolution(self):
        from src.modules.media.domain.entities import Movie
        from src.modules.media.domain.value_objects import FilePath, MediaFile, Resolution

        movie = Movie.create(
            title="Inception",
            year=2010,
            duration=8880,
            file_path="/movies/inception_720p.mkv",
            file_size=2_000_000_000,
            resolution="720p",
        )
        movie = movie.with_file(
            MediaFile(
                file_path=FilePath("/movies/inception_4k.mkv"),
                file_size=20_000_000_000,
                resolution=Resolution("4K"),
            )
        )

        best = movie.best_file
        assert best is not None
        assert best.resolution.name == "4K"

    def test_available_resolutions_should_be_sorted_highest_first(self):
        from src.modules.media.domain.entities import Movie
        from src.modules.media.domain.value_objects import FilePath, MediaFile, Resolution

        movie = Movie.create(
            title="Inception",
            year=2010,
            duration=8880,
            file_path="/movies/inception_720p.mkv",
            file_size=2_000_000_000,
            resolution="720p",
        )
        movie = movie.with_file(
            MediaFile(
                file_path=FilePath("/movies/inception_4k.mkv"),
                file_size=20_000_000_000,
                resolution=Resolution("4K"),
            )
        )

        resolutions = movie.available_resolutions
        assert [r.name for r in resolutions] == ["4K", "720p"]

    def test_total_size_should_sum_all_files(self):
        from src.modules.media.domain.entities import Movie
        from src.modules.media.domain.value_objects import FilePath, MediaFile, Resolution

        movie = Movie.create(
            title="Inception",
            year=2010,
            duration=8880,
            file_path="/movies/inception_1080p.mkv",
            file_size=4_000_000_000,
            resolution="1080p",
        )
        movie = movie.with_file(
            MediaFile(
                file_path=FilePath("/movies/inception_4k.mkv"),
                file_size=20_000_000_000,
                resolution=Resolution("4K"),
            )
        )

        assert movie.total_size == 24_000_000_000

    def test_with_file_should_add_new_variant(self):
        from src.modules.media.domain.entities import Movie
        from src.modules.media.domain.value_objects import FilePath, MediaFile, Resolution

        movie = Movie.create(
            title="Inception",
            year=2010,
            duration=8880,
            file_path="/movies/inception.mkv",
            file_size=4_000_000_000,
            resolution="1080p",
        )

        movie = movie.with_file(
            MediaFile(
                file_path=FilePath("/movies/inception_4k.mkv"),
                file_size=20_000_000_000,
                resolution=Resolution("4K"),
            )
        )

        assert len(movie.files) == 2

    def test_with_file_should_not_add_duplicate_path(self):
        from src.modules.media.domain.entities import Movie

        movie = Movie.create(
            title="Inception",
            year=2010,
            duration=8880,
            file_path="/movies/inception.mkv",
            file_size=4_000_000_000,
            resolution="1080p",
        )

        from src.modules.media.domain.value_objects import FilePath, MediaFile, Resolution

        result = movie.with_file(
            MediaFile(
                file_path=FilePath("/movies/inception.mkv"),
                file_size=4_000_000_000,
                resolution=Resolution("1080p"),
            )
        )

        assert result is movie  # same object, no change

    def test_get_file_by_resolution_should_find_match(self):
        from src.modules.media.domain.entities import Movie

        movie = Movie.create(
            title="Inception",
            year=2010,
            duration=8880,
            file_path="/movies/inception.mkv",
            file_size=4_000_000_000,
            resolution="1080p",
        )

        found = movie.get_file_by_resolution("1080p")
        assert found is not None
        assert found.resolution.name == "1080p"

    def test_get_file_by_resolution_should_return_none_when_not_found(self):
        from src.modules.media.domain.entities import Movie

        movie = Movie.create(
            title="Inception",
            year=2010,
            duration=8880,
            file_path="/movies/inception.mkv",
            file_size=4_000_000_000,
            resolution="1080p",
        )

        found = movie.get_file_by_resolution("4K")
        assert found is None


class TestMovieEquality:
    """Tests for Movie equality based on ID."""

    def test_should_be_equal_when_same_id(self):
        from src.modules.media.domain.entities import Movie
        from src.modules.media.domain.value_objects import (
            Duration,
            MovieId,
            Title,
            Year,
        )

        movie_id = MovieId.generate()

        movie1 = Movie(
            id=movie_id,
            title=Title("Inception"),
            year=Year(2010),
            duration=Duration(8880),
        )

        movie2 = Movie(
            id=movie_id,
            title=Title("Different"),
            year=Year(2010),
            duration=Duration(8880),
        )

        assert movie1 == movie2


class TestMovieEvents:
    """Tests for Movie domain events."""

    def test_should_add_and_pull_events(self):
        from src.modules.media.domain.entities import Movie

        movie = Movie.create(
            title="Inception",
            year=2010,
            duration=8880,
            file_path="/movies/inception.mkv",
            file_size=4_000_000_000,
            resolution="1080p",
        )

        movie.add_event({"type": "MovieCreated", "movie_id": str(movie.id)})

        assert movie.has_pending_events is True

        events = movie.pull_events()

        assert len(events) == 1
        assert movie.has_pending_events is False


class TestMovieImmutability:
    """Tests for Movie frozen (immutable) behavior."""

    def test_should_reject_direct_attribute_assignment(self):
        from src.modules.media.domain.entities import Movie

        movie = Movie.create(
            title="Inception",
            year=2010,
            duration=8880,
            file_path="/movies/inception.mkv",
            file_size=4_000_000_000,
            resolution="1080p",
        )

        with pytest.raises(DomainValidationException):
            movie.year = 2020  # type: ignore[assignment, misc]

    def test_with_genre_should_return_new_instance(self):
        from src.modules.media.domain.entities import Movie

        movie = Movie.create(
            title="Inception",
            year=2010,
            duration=8880,
            file_path="/movies/inception.mkv",
            file_size=4_000_000_000,
            resolution="1080p",
        )

        updated = movie.with_genre("Sci-Fi")

        assert updated is not movie
        assert len(updated.genres) == 1
        assert len(movie.genres) == 0

    def test_with_genre_duplicate_string_should_return_self(self):
        from src.modules.media.domain.entities import Movie

        movie = Movie.create(
            title="Inception",
            year=2010,
            duration=8880,
            file_path="/movies/inception.mkv",
            file_size=4_000_000_000,
            resolution="1080p",
        )
        movie = movie.with_genre("Sci-Fi")

        result = movie.with_genre("Sci-Fi")

        assert result is movie

    def test_with_genre_duplicate_value_object_should_return_self(self):
        from src.modules.media.domain.entities import Movie
        from src.modules.media.domain.value_objects import Genre

        movie = Movie.create(
            title="Inception",
            year=2010,
            duration=8880,
            file_path="/movies/inception.mkv",
            file_size=4_000_000_000,
            resolution="1080p",
        )
        movie = movie.with_genre(Genre("Sci-Fi"))

        result = movie.with_genre(Genre("Sci-Fi"))

        assert result is movie

    def test_with_file_should_return_new_instance(self):
        from src.modules.media.domain.entities import Movie
        from src.modules.media.domain.value_objects import FilePath, MediaFile, Resolution

        movie = Movie.create(
            title="Inception",
            year=2010,
            duration=8880,
            file_path="/movies/inception.mkv",
            file_size=4_000_000_000,
            resolution="1080p",
        )

        updated = movie.with_file(
            MediaFile(
                file_path=FilePath("/movies/inception_4k.mkv"),
                file_size=20_000_000_000,
                resolution=Resolution("4K"),
            )
        )

        assert updated is not movie
        assert len(updated.files) == 2
        assert len(movie.files) == 1
