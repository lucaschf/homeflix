"""Tests for EpisodeCompositeId."""

import pytest

from src.building_blocks.domain.errors import DomainValidationException
from src.shared_kernel.value_objects.episode_composite_id import (
    EpisodeCompositeId,
    EpisodeCompositeIdRuleCodes,
)
from src.shared_kernel.value_objects.media_id import SeriesId


class TestEpisodeCompositeIdBuild:
    """Tests for building composite IDs."""

    def test_build_creates_correct_media_id(self):
        eid = EpisodeCompositeId.build(SeriesId("ser_Hy9VjMfILYZe"), 3, 2)
        assert eid.media_id == "epi_ser_Hy9VjMfILYZe_3_2"

    def test_build_stores_components(self):
        eid = EpisodeCompositeId.build(SeriesId("ser_abc123def456"), 1, 5)
        assert eid.series_id == SeriesId("ser_abc123def456")
        assert eid.season_number == 1
        assert eid.episode_number == 5

    def test_build_with_large_numbers(self):
        eid = EpisodeCompositeId.build(SeriesId("ser_XXXXXXXXXXXX"), 25, 100)
        assert eid.media_id == "epi_ser_XXXXXXXXXXXX_25_100"


class TestEpisodeCompositeIdPrefix:
    """Tests for the shared series prefix."""

    def test_prefix_matches_built_media_id(self):
        series_id = SeriesId("ser_Hy9VjMfILYZe")
        prefix = EpisodeCompositeId.media_id_prefix_for(series_id)
        assert prefix == "epi_ser_Hy9VjMfILYZe_"
        assert EpisodeCompositeId.build(series_id, 3, 2).media_id.startswith(prefix)


class TestEpisodeCompositeIdParse:
    """Tests for parsing composite IDs."""

    def test_parse_valid_composite_id(self):
        eid = EpisodeCompositeId.parse("epi_ser_Hy9VjMfILYZe_3_2")
        assert eid is not None
        assert eid.series_id == SeriesId("ser_Hy9VjMfILYZe")
        assert eid.season_number == 3
        assert eid.episode_number == 2

    def test_parse_returns_none_for_standard_episode_id(self):
        assert EpisodeCompositeId.parse("epi_03ZzYaQ77FaB") is None

    def test_parse_returns_none_for_movie_id(self):
        assert EpisodeCompositeId.parse("mov_abc123def456") is None

    def test_parse_returns_none_for_empty_string(self):
        assert EpisodeCompositeId.parse("") is None

    def test_parse_returns_none_for_wrong_inner_prefix(self):
        # No 'epi_ser_' marker → not a composite episode key at all.
        assert EpisodeCompositeId.parse("epi_mov_something_1_2") is None

    def test_parse_raises_for_non_numeric_season(self):
        with pytest.raises(DomainValidationException):
            EpisodeCompositeId.parse("epi_ser_Hy9VjMfILYZe_abc_2")

    def test_parse_raises_for_non_numeric_episode(self):
        with pytest.raises(DomainValidationException):
            EpisodeCompositeId.parse("epi_ser_Hy9VjMfILYZe_3_abc")

    def test_parse_raises_for_missing_segments(self):
        with pytest.raises(DomainValidationException):
            EpisodeCompositeId.parse("epi_ser_Hy9VjMfILYZe")

    def test_parse_raises_for_invalid_series_id(self):
        # Marker present but the series part is not a valid SeriesId.
        with pytest.raises(DomainValidationException):
            EpisodeCompositeId.parse("epi_ser_short_3_2")

    @pytest.mark.parametrize(
        "malformed",
        [
            "epi_ser_Hy9VjMfILYZe_abc_2",  # non-numeric season
            "epi_ser_Hy9VjMfILYZe",  # missing segments
            "epi_ser_short_3_2",  # invalid series id
        ],
    )
    def test_parse_malformed_uses_uniform_rule_code(self, malformed: str) -> None:
        # Every marker-bearing-but-broken shape surfaces under the same code,
        # regardless of which sub-path (structure, numbers, series id) failed.
        with pytest.raises(DomainValidationException) as exc_info:
            EpisodeCompositeId.parse(malformed)
        assert (
            exc_info.value.message_code
            == EpisodeCompositeIdRuleCodes.MALFORMED_COMPOSITE_EPISODE_ID
        )


class TestEpisodeCompositeIdRoundTrip:
    """Tests for build/parse symmetry."""

    @pytest.mark.parametrize(
        ("series_id", "season", "episode"),
        [
            ("ser_Hy9VjMfILYZe", 3, 2),
            ("ser_abc123def456", 1, 1),
            ("ser_XXXXXXXXXXXX", 10, 25),
        ],
    )
    def test_round_trip(self, series_id: str, season: int, episode: int) -> None:
        built = EpisodeCompositeId.build(SeriesId(series_id), season, episode)
        parsed = EpisodeCompositeId.parse(built.media_id)
        assert parsed is not None
        assert parsed.series_id == SeriesId(series_id)
        assert parsed.season_number == season
        assert parsed.episode_number == episode
