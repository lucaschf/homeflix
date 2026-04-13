"""Tests for EpisodeNumber value object."""

import pytest

from src.building_blocks.domain.errors import DomainValidationException


class TestEpisodeNumberCreation:
    """Tests for EpisodeNumber instantiation."""

    def test_should_create_with_valid_number(self):
        from src.modules.media.domain.value_objects import EpisodeNumber

        episode = EpisodeNumber(1)

        assert episode.value == 1

    def test_should_raise_error_for_zero(self):
        from src.modules.media.domain.value_objects import EpisodeNumber

        with pytest.raises(DomainValidationException, match="at least 1"):
            EpisodeNumber(0)

    def test_should_raise_error_for_negative_number(self):
        from src.modules.media.domain.value_objects import EpisodeNumber

        with pytest.raises(DomainValidationException, match="at least 1"):
            EpisodeNumber(-1)

    def test_should_raise_error_for_non_integer(self):
        from src.modules.media.domain.value_objects import EpisodeNumber

        with pytest.raises(DomainValidationException):
            EpisodeNumber("1")  # type: ignore[arg-type]


class TestEpisodeNumberComparison:
    """Tests for EpisodeNumber comparison operators."""

    def test_should_compare_equal(self):
        from src.modules.media.domain.value_objects import EpisodeNumber

        assert EpisodeNumber(1) == EpisodeNumber(1)

    def test_should_compare_less_than(self):
        from src.modules.media.domain.value_objects import EpisodeNumber

        assert EpisodeNumber(1) < EpisodeNumber(2)

    def test_should_be_hashable(self):
        from src.modules.media.domain.value_objects import EpisodeNumber

        episode = EpisodeNumber(3)

        assert episode in {episode}


class TestEpisodeNumberImmutability:
    """Tests for EpisodeNumber immutability."""

    def test_should_be_immutable(self):
        from src.modules.media.domain.value_objects import EpisodeNumber

        episode = EpisodeNumber(1)

        with pytest.raises(DomainValidationException):
            episode.root = 2  # type: ignore[misc]
