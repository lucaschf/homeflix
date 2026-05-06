"""Tests for ImdbId value object."""

import pytest

from src.building_blocks.domain.errors import DomainValidationException


class TestImdbIdCreation:
    """Tests for ImdbId instantiation."""

    def test_should_create_with_valid_id(self):
        from src.modules.media.domain.value_objects import ImdbId

        imdb_id = ImdbId("tt1375666")

        assert imdb_id.value == "tt1375666"

    def test_should_create_with_long_id(self):
        from src.modules.media.domain.value_objects import ImdbId

        imdb_id = ImdbId("tt12345678")

        assert imdb_id.value == "tt12345678"

    def test_should_raise_error_for_missing_prefix(self):
        from src.modules.media.domain.value_objects import ImdbId

        with pytest.raises(DomainValidationException, match="tt"):
            ImdbId("1375666")

    def test_should_raise_error_for_short_digits(self):
        from src.modules.media.domain.value_objects import ImdbId

        with pytest.raises(DomainValidationException, match="tt"):
            ImdbId("tt12345")

    def test_should_raise_error_for_invalid_format(self):
        from src.modules.media.domain.value_objects import ImdbId

        with pytest.raises(DomainValidationException, match="tt followed by 7"):
            ImdbId("invalid")

    def test_should_raise_error_for_non_string_input(self):
        from src.modules.media.domain.value_objects import ImdbId

        with pytest.raises(DomainValidationException, match="must be a string"):
            ImdbId(1234567)  # type: ignore[arg-type]


class TestImdbIdBehavior:
    """Tests for ImdbId value object behavior."""

    def test_str_should_return_string_value(self):
        from src.modules.media.domain.value_objects import ImdbId

        assert str(ImdbId("tt1375666")) == "tt1375666"

    def test_should_be_equal_when_same_value(self):
        from src.modules.media.domain.value_objects import ImdbId

        assert ImdbId("tt1375666") == ImdbId("tt1375666")

    def test_should_not_be_equal_when_different_value(self):
        from src.modules.media.domain.value_objects import ImdbId

        assert ImdbId("tt1375666") != ImdbId("tt0903747")

    def test_should_be_hashable(self):
        from src.modules.media.domain.value_objects import ImdbId

        ids = {ImdbId("tt1375666"), ImdbId("tt1375666")}

        assert len(ids) == 1
