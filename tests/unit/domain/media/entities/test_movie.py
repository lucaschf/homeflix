"""Tests for Movie aggregate root."""

import pytest

from src.domain.shared.exceptions.domain import DomainValidationException


class TestMovieCreation:
    """Tests for Movie instantiation."""

    def test_should_create_with_required_fields(self):
        from src.domain.media.entities import Movie
        from src.domain.media.value_objects import (
            Duration,
            FilePath,
            Resolution,
            Title,
            Year,
        )

        movie = Movie(
            title=Title("Inception"),
            year=Year(2010),
            duration=Duration(8880),
            file_path=FilePath("/movies/inception.mkv"),
            file_size=4_000_000_000,
            resolution=Resolution("1080p"),
        )

        assert movie.id is None
        assert movie.title.value == "Inception"
        assert movie.year.value == 2010

    def test_should_create_via_factory_with_auto_id(self):
        from src.domain.media.entities import Movie
        from src.domain.media.value_objects import MovieId

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

    def test_should_accept_string_id_and_convert(self):
        from src.domain.media.entities import Movie
        from src.domain.media.value_objects import (
            Duration,
            FilePath,
            MovieId,
            Resolution,
            Title,
            Year,
        )

        movie = Movie(
            id="mov_abc123abc123",
            title=Title("Inception"),
            year=Year(2010),
            duration=Duration(8880),
            file_path=FilePath("/movies/inception.mkv"),
            file_size=4_000_000_000,
            resolution=Resolution("1080p"),
        )

        assert isinstance(movie.id, MovieId)

    def test_should_raise_error_for_negative_file_size(self):
        from src.domain.media.entities import Movie
        from src.domain.media.value_objects import (
            Duration,
            FilePath,
            Resolution,
            Title,
            Year,
        )

        with pytest.raises(DomainValidationException):
            Movie(
                title=Title("Inception"),
                year=Year(2010),
                duration=Duration(8880),
                file_path=FilePath("/movies/inception.mkv"),
                file_size=-1,
                resolution=Resolution("1080p"),
            )


class TestMovieOptionalFields:
    """Tests for Movie optional fields."""

    def test_should_create_with_all_optional_fields(self):
        from src.domain.media.entities import Movie
        from src.domain.media.value_objects import (
            Duration,
            FilePath,
            Genre,
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
            file_path=FilePath("/movies/inception.mkv"),
            file_size=4_000_000_000,
            resolution=Resolution("1080p"),
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
        from src.domain.media.entities import Movie

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
        from src.domain.media.entities import Movie
        from src.domain.media.value_objects import Genre

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
        from src.domain.media.entities import Movie

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


class TestMovieEquality:
    """Tests for Movie equality based on ID."""

    def test_should_be_equal_when_same_id(self):
        from src.domain.media.entities import Movie
        from src.domain.media.value_objects import (
            Duration,
            FilePath,
            MovieId,
            Resolution,
            Title,
            Year,
        )

        movie_id = MovieId.generate()

        movie1 = Movie(
            id=movie_id,
            title=Title("Inception"),
            year=Year(2010),
            duration=Duration(8880),
            file_path=FilePath("/movies/inception.mkv"),
            file_size=4_000_000_000,
            resolution=Resolution("1080p"),
        )

        movie2 = Movie(
            id=movie_id,
            title=Title("Different"),
            year=Year(2010),
            duration=Duration(8880),
            file_path=FilePath("/movies/inception.mkv"),
            file_size=4_000_000_000,
            resolution=Resolution("1080p"),
        )

        assert movie1 == movie2


class TestMovieEvents:
    """Tests for Movie domain events."""

    def test_should_add_and_pull_events(self):
        from src.domain.media.entities import Movie

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
