"""Tests for Media domain external IDs."""

import pytest

from src.domain.shared.exceptions.domain import DomainValidationException
from src.domain.shared.models.external_id import RANDOM_PART_LENGTH


class TestMovieIdCreation:
    """Tests for MovieId instantiation."""

    def test_should_create_with_valid_format(self):
        from src.domain.media.value_objects import MovieId

        movie_id = MovieId("mov_abc123abc123")

        assert movie_id.value == "mov_abc123abc123"

    def test_should_have_mov_prefix(self):
        from src.domain.media.value_objects import MovieId

        movie_id = MovieId("mov_abc123abc123")

        assert movie_id.prefix == "mov"

    def test_should_raise_error_for_wrong_prefix(self):
        from src.domain.media.value_objects import MovieId

        with pytest.raises(DomainValidationException, match="prefix"):
            MovieId("ser_abc123abc123")

    def test_should_raise_error_for_invalid_format(self):
        from src.domain.media.value_objects import MovieId

        with pytest.raises(DomainValidationException):
            MovieId("mov_short")


class TestMovieIdGeneration:
    """Tests for MovieId.generate()."""

    def test_should_generate_with_mov_prefix(self):
        from src.domain.media.value_objects import MovieId

        movie_id = MovieId.generate()

        assert movie_id.prefix == "mov"

    def test_should_generate_with_correct_random_part_length(self):
        from src.domain.media.value_objects import MovieId

        movie_id = MovieId.generate()

        assert len(movie_id.random_part) == RANDOM_PART_LENGTH

    def test_should_generate_unique_ids(self):
        from src.domain.media.value_objects import MovieId

        ids = [MovieId.generate() for _ in range(100)]
        unique_ids = {id_.value for id_ in ids}

        assert len(unique_ids) == 100


class TestSeriesIdCreation:
    """Tests for SeriesId instantiation."""

    def test_should_create_with_valid_format(self):
        from src.domain.media.value_objects import SeriesId

        series_id = SeriesId("ser_abc123abc123")

        assert series_id.value == "ser_abc123abc123"

    def test_should_have_ser_prefix(self):
        from src.domain.media.value_objects import SeriesId

        series_id = SeriesId("ser_abc123abc123")

        assert series_id.prefix == "ser"

    def test_should_raise_error_for_wrong_prefix(self):
        from src.domain.media.value_objects import SeriesId

        with pytest.raises(DomainValidationException, match="prefix"):
            SeriesId("mov_abc123abc123")


class TestSeriesIdGeneration:
    """Tests for SeriesId.generate()."""

    def test_should_generate_with_ser_prefix(self):
        from src.domain.media.value_objects import SeriesId

        series_id = SeriesId.generate()

        assert series_id.prefix == "ser"

    def test_should_generate_unique_ids(self):
        from src.domain.media.value_objects import SeriesId

        ids = [SeriesId.generate() for _ in range(100)]
        unique_ids = {id_.value for id_ in ids}

        assert len(unique_ids) == 100


class TestSeasonIdCreation:
    """Tests for SeasonId instantiation."""

    def test_should_create_with_valid_format(self):
        from src.domain.media.value_objects import SeasonId

        season_id = SeasonId("ssn_abc123abc123")

        assert season_id.value == "ssn_abc123abc123"

    def test_should_have_ssn_prefix(self):
        from src.domain.media.value_objects import SeasonId

        season_id = SeasonId("ssn_abc123abc123")

        assert season_id.prefix == "ssn"

    def test_should_raise_error_for_wrong_prefix(self):
        from src.domain.media.value_objects import SeasonId

        with pytest.raises(DomainValidationException, match="prefix"):
            SeasonId("mov_abc123abc123")


class TestSeasonIdGeneration:
    """Tests for SeasonId.generate()."""

    def test_should_generate_with_ssn_prefix(self):
        from src.domain.media.value_objects import SeasonId

        season_id = SeasonId.generate()

        assert season_id.prefix == "ssn"

    def test_should_generate_unique_ids(self):
        from src.domain.media.value_objects import SeasonId

        ids = [SeasonId.generate() for _ in range(100)]
        unique_ids = {id_.value for id_ in ids}

        assert len(unique_ids) == 100


class TestEpisodeIdCreation:
    """Tests for EpisodeId instantiation."""

    def test_should_create_with_valid_format(self):
        from src.domain.media.value_objects import EpisodeId

        episode_id = EpisodeId("epi_abc123abc123")

        assert episode_id.value == "epi_abc123abc123"

    def test_should_have_epi_prefix(self):
        from src.domain.media.value_objects import EpisodeId

        episode_id = EpisodeId("epi_abc123abc123")

        assert episode_id.prefix == "epi"

    def test_should_raise_error_for_wrong_prefix(self):
        from src.domain.media.value_objects import EpisodeId

        with pytest.raises(DomainValidationException, match="prefix"):
            EpisodeId("mov_abc123abc123")


class TestEpisodeIdGeneration:
    """Tests for EpisodeId.generate()."""

    def test_should_generate_with_epi_prefix(self):
        from src.domain.media.value_objects import EpisodeId

        episode_id = EpisodeId.generate()

        assert episode_id.prefix == "epi"

    def test_should_generate_unique_ids(self):
        from src.domain.media.value_objects import EpisodeId

        ids = [EpisodeId.generate() for _ in range(100)]
        unique_ids = {id_.value for id_ in ids}

        assert len(unique_ids) == 100


class TestMediaIdEquality:
    """Tests for MediaId equality between different types."""

    def test_movie_id_should_not_equal_series_id_with_same_random_part(self):
        from src.domain.media.value_objects import MovieId, SeriesId

        movie_id = MovieId("mov_abc123abc123")
        series_id = SeriesId("ser_abc123abc123")

        assert movie_id.random_part == series_id.random_part
        assert movie_id != series_id

    def test_same_movie_ids_should_be_equal(self):
        from src.domain.media.value_objects import MovieId

        id1 = MovieId("mov_abc123abc123")
        id2 = MovieId("mov_abc123abc123")

        assert id1 == id2

    def test_movie_id_should_be_hashable(self):
        from src.domain.media.value_objects import MovieId

        movie_id = MovieId("mov_abc123abc123")

        id_set = {movie_id}

        assert movie_id in id_set


class TestParseMediaId:
    """Tests for parse_media_id function."""

    def test_should_parse_movie_id(self):
        from src.domain.media.value_objects import MovieId, parse_media_id

        result = parse_media_id("mov_abc123abc123")

        assert isinstance(result, MovieId)
        assert result.value == "mov_abc123abc123"

    def test_should_parse_series_id(self):
        from src.domain.media.value_objects import SeriesId, parse_media_id

        result = parse_media_id("ser_abc123abc123")

        assert isinstance(result, SeriesId)
        assert result.value == "ser_abc123abc123"

    def test_should_parse_episode_id(self):
        from src.domain.media.value_objects import EpisodeId, parse_media_id

        result = parse_media_id("epi_abc123abc123")

        assert isinstance(result, EpisodeId)
        assert result.value == "epi_abc123abc123"

    def test_should_parse_season_id(self):
        from src.domain.media.value_objects import SeasonId, parse_media_id

        result = parse_media_id("ssn_abc123abc123")

        assert isinstance(result, SeasonId)
        assert result.value == "ssn_abc123abc123"

    def test_should_raise_error_for_unknown_prefix(self):
        from src.domain.media.value_objects import parse_media_id

        with pytest.raises(DomainValidationException, match="Unknown media prefix"):
            parse_media_id("xyz_abc123abc123")

    def test_should_raise_error_for_invalid_format(self):
        from src.domain.media.value_objects import parse_media_id

        with pytest.raises(DomainValidationException, match="Invalid media ID format"):
            parse_media_id("invalidformat")

    def test_should_raise_error_for_empty_string(self):
        from src.domain.media.value_objects import parse_media_id

        with pytest.raises(DomainValidationException, match="Invalid media ID format"):
            parse_media_id("")
