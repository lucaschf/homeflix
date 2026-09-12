"""Tests for the Certification ↔ three-column mapping (ADR-035)."""

from datetime import UTC, datetime

import pytest

from src.modules.media.domain.entities import Movie, Series
from src.modules.media.domain.value_objects import (
    AgeRating,
    Certification,
    ContentRating,
    Duration,
    FilePath,
    MediaFile,
    MovieId,
    RatingSystem,
    Resolution,
    SeriesId,
    Title,
    Year,
)
from src.modules.media.infrastructure.persistence.mappers import MovieMapper, SeriesMapper
from src.modules.media.infrastructure.persistence.mappers._certification import (
    certification_from_columns,
    certification_to_columns,
)
from src.modules.media.infrastructure.persistence.models import MovieModel, SeriesModel

_LIBRARY_ID = "lib_test12345678"
_NOW = datetime(2026, 9, 12, 12, 0, tzinfo=UTC)


def _stamp(model):
    """Fill the timestamps the database would supply on INSERT."""
    model.created_at = _NOW
    model.updated_at = _NOW
    return model


PG13 = Certification(
    system=RatingSystem.US_MPA,
    label=ContentRating("PG-13"),
    minimum_age=AgeRating(13),
)
UNRATED = Certification.undetermined(ContentRating("NR"))


def _movie(certification: Certification | None) -> Movie:
    return Movie(
        library_id=_LIBRARY_ID,
        id=MovieId.generate(),
        title=Title("Test Movie"),
        year=Year(2024),
        duration=Duration(7200),
        certification=certification,
        files=[
            MediaFile(
                file_path=FilePath("/movies/test.mkv"),
                file_size=1_000_000_000,
                resolution=Resolution("1080p"),
                is_primary=True,
            )
        ],
    )


def _series(certification: Certification | None) -> Series:
    return Series(
        library_id=_LIBRARY_ID,
        id=SeriesId.generate(),
        title=Title("Test Series"),
        start_year=Year(2024),
        certification=certification,
    )


@pytest.mark.unit
class TestColumnHelpers:
    """The flattening in both directions."""

    def test_should_split_a_certification_into_three_columns(self):
        assert certification_to_columns(PG13) == ("PG-13", 13, "us_mpa")

    def test_should_keep_the_label_when_the_age_is_undetermined(self):
        assert certification_to_columns(UNRATED) == ("NR", None, "unknown")

    def test_should_flatten_none_to_three_nulls(self):
        assert certification_to_columns(None) == (None, None, None)

    def test_should_rebuild_from_columns(self):
        model = MovieModel(content_rating="PG-13", minimum_age=13, rating_system="us_mpa")

        assert certification_from_columns(model) == PG13

    def test_should_read_a_missing_label_as_no_certification(self):
        """An age without a label is corruption, not a certification."""
        model = MovieModel(content_rating=None, minimum_age=13, rating_system="us_mpa")

        assert certification_from_columns(model) is None

    def test_should_degrade_an_unknown_system_instead_of_raising(self):
        """A mapper that throws takes the whole catalog page down."""
        model = MovieModel(content_rating="16", minimum_age=16, rating_system="fsk_de")

        rebuilt = certification_from_columns(model)

        assert rebuilt is not None
        assert rebuilt.system is RatingSystem.UNKNOWN
        assert rebuilt.minimum_age == AgeRating(16)

    def test_should_treat_a_missing_system_as_unknown(self):
        model = MovieModel(content_rating="12", minimum_age=12, rating_system=None)

        assert certification_from_columns(model).system is RatingSystem.UNKNOWN


@pytest.mark.unit
class TestMovieRoundTrip:
    """Entity → model → entity through MovieMapper."""

    @pytest.mark.parametrize("certification", [PG13, UNRATED, None])
    def test_should_survive_a_round_trip(self, certification):
        movie = _movie(certification)

        rebuilt = MovieMapper.to_entity(_stamp(MovieMapper.to_model(movie)))

        assert rebuilt.certification == certification

    def test_should_write_all_three_columns(self):
        model = MovieMapper.to_model(_movie(PG13))

        assert (model.content_rating, model.minimum_age, model.rating_system) == (
            "PG-13",
            13,
            "us_mpa",
        )

    def test_update_model_should_overwrite_all_three_columns(self):
        model = MovieMapper.to_model(_movie(PG13))

        MovieMapper.update_model(model, _movie(None))

        assert (model.content_rating, model.minimum_age, model.rating_system) == (None, None, None)

    def test_should_expose_the_label_through_the_display_accessor(self):
        assert _movie(PG13).content_rating == ContentRating("PG-13")
        assert _movie(None).content_rating is None

    def test_should_expose_the_age_through_the_filter_accessor(self):
        assert _movie(PG13).minimum_age == AgeRating(13)
        assert _movie(UNRATED).minimum_age is None


@pytest.mark.unit
class TestSeriesRoundTrip:
    """Entity → model → entity through SeriesMapper."""

    @pytest.mark.parametrize("certification", [PG13, UNRATED, None])
    def test_should_survive_a_round_trip(self, certification):
        series = _series(certification)

        rebuilt = SeriesMapper.to_entity(_stamp(SeriesMapper.to_model(series)))

        assert rebuilt.certification == certification

    def test_should_write_all_three_columns(self):
        model = SeriesMapper.to_model(_series(PG13))

        assert (model.content_rating, model.minimum_age, model.rating_system) == (
            "PG-13",
            13,
            "us_mpa",
        )

    def test_update_model_should_overwrite_all_three_columns(self):
        model = SeriesModel(
            external_id="ser_test12345",
            library_id=_LIBRARY_ID,
            title="Test Series",
            start_year=2024,
        )

        SeriesMapper.update_model(model, _series(PG13))

        assert model.minimum_age == 13
        assert model.rating_system == "us_mpa"
