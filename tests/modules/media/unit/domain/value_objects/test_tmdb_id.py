"""Tests for TmdbId value object."""

import pytest

from src.building_blocks.domain.errors import DomainValidationException


class TestTmdbIdCreation:
    """Tests for TmdbId instantiation."""

    def test_should_create_with_valid_id(self):
        from src.modules.media.domain.value_objects import TmdbId

        tmdb_id = TmdbId(27205)

        assert tmdb_id.value == 27205

    def test_should_create_with_small_id(self):
        from src.modules.media.domain.value_objects import TmdbId

        tmdb_id = TmdbId(1)

        assert tmdb_id.value == 1

    def test_should_raise_error_for_zero(self):
        from src.modules.media.domain.value_objects import TmdbId

        with pytest.raises(DomainValidationException, match="positive"):
            TmdbId(0)

    def test_should_raise_error_for_negative(self):
        from src.modules.media.domain.value_objects import TmdbId

        with pytest.raises(DomainValidationException, match="positive"):
            TmdbId(-1)


class TestTmdbIdBehavior:
    """Tests for TmdbId value object behavior."""

    def test_str_should_return_string_value(self):
        from src.modules.media.domain.value_objects import TmdbId

        assert str(TmdbId(27205)) == "27205"

    def test_should_be_equal_when_same_value(self):
        from src.modules.media.domain.value_objects import TmdbId

        assert TmdbId(27205) == TmdbId(27205)

    def test_should_not_be_equal_when_different_value(self):
        from src.modules.media.domain.value_objects import TmdbId

        assert TmdbId(27205) != TmdbId(1396)

    def test_should_be_hashable(self):
        from src.modules.media.domain.value_objects import TmdbId

        ids = {TmdbId(27205), TmdbId(27205)}

        assert len(ids) == 1
