"""Tests for EpisodeCompositeId."""

import pytest

from src.shared_kernel.episode_composite_id import EpisodeCompositeId


class TestEpisodeCompositeIdBuild:
    """Tests for building composite IDs."""

    def test_build_creates_correct_media_id(self):
        eid = EpisodeCompositeId.build("ser_Hy9VjMfILYZe", 3, 2)
        assert eid.media_id == "epi_ser_Hy9VjMfILYZe_3_2"

    def test_build_stores_components(self):
        eid = EpisodeCompositeId.build("ser_abc123def456", 1, 5)
        assert eid.series_id == "ser_abc123def456"
        assert eid.season_number == 1
        assert eid.episode_number == 5

    def test_build_with_large_numbers(self):
        eid = EpisodeCompositeId.build("ser_XXXXXXXXXXXX", 25, 100)
        assert eid.media_id == "epi_ser_XXXXXXXXXXXX_25_100"


class TestEpisodeCompositeIdParse:
    """Tests for parsing composite IDs."""

    def test_parse_valid_composite_id(self):
        eid = EpisodeCompositeId.parse("epi_ser_Hy9VjMfILYZe_3_2")
        assert eid is not None
        assert eid.series_id == "ser_Hy9VjMfILYZe"
        assert eid.season_number == 3
        assert eid.episode_number == 2

    def test_parse_returns_none_for_standard_episode_id(self):
        assert EpisodeCompositeId.parse("epi_03ZzYaQ77FaB") is None

    def test_parse_returns_none_for_movie_id(self):
        assert EpisodeCompositeId.parse("mov_abc123def456") is None

    def test_parse_returns_none_for_empty_string(self):
        assert EpisodeCompositeId.parse("") is None

    def test_parse_returns_none_for_non_numeric_season(self):
        assert EpisodeCompositeId.parse("epi_ser_Hy9VjMfILYZe_abc_2") is None

    def test_parse_returns_none_for_non_numeric_episode(self):
        assert EpisodeCompositeId.parse("epi_ser_Hy9VjMfILYZe_3_abc") is None

    def test_parse_returns_none_for_missing_segments(self):
        assert EpisodeCompositeId.parse("epi_ser_Hy9VjMfILYZe") is None

    def test_parse_returns_none_for_wrong_prefix(self):
        assert EpisodeCompositeId.parse("epi_mov_something_1_2") is None


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
        built = EpisodeCompositeId.build(series_id, season, episode)
        parsed = EpisodeCompositeId.parse(built.media_id)
        assert parsed is not None
        assert parsed.series_id == series_id
        assert parsed.season_number == season
        assert parsed.episode_number == episode
