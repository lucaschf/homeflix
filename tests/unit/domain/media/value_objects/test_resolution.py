"""Tests for Resolution value object."""

import pytest

from src.domain.shared.exceptions.domain import DomainValidationException


class TestResolutionCreation:
    """Tests for Resolution instantiation."""

    def test_should_create_with_360p(self):
        from src.domain.media.value_objects import Resolution

        resolution = Resolution("360p")

        assert resolution.value == "360p"

    def test_should_create_with_480p(self):
        from src.domain.media.value_objects import Resolution

        resolution = Resolution("480p")

        assert resolution.value == "480p"

    def test_should_create_with_720p(self):
        from src.domain.media.value_objects import Resolution

        resolution = Resolution("720p")

        assert resolution.value == "720p"

    def test_should_create_with_1080p(self):
        from src.domain.media.value_objects import Resolution

        resolution = Resolution("1080p")

        assert resolution.value == "1080p"

    def test_should_create_with_2k(self):
        from src.domain.media.value_objects import Resolution

        resolution = Resolution("2K")

        assert resolution.value == "2K"

    def test_should_create_with_4k(self):
        from src.domain.media.value_objects import Resolution

        resolution = Resolution("4K")

        assert resolution.value == "4K"

    def test_should_create_with_unknown(self):
        from src.domain.media.value_objects import Resolution

        resolution = Resolution("Unknown")

        assert resolution.value == "Unknown"

    def test_should_strip_whitespace(self):
        from src.domain.media.value_objects import Resolution

        resolution = Resolution("  1080p  ")

        assert resolution.value == "1080p"

    def test_should_raise_error_for_invalid_resolution(self):
        from src.domain.media.value_objects import Resolution

        with pytest.raises(DomainValidationException, match="must be one of"):
            Resolution("240p")

    def test_should_raise_error_for_empty_string(self):
        from src.domain.media.value_objects import Resolution

        with pytest.raises(DomainValidationException):
            Resolution("")

    def test_should_raise_error_for_non_string_input(self):
        from src.domain.media.value_objects import Resolution

        with pytest.raises(DomainValidationException):
            Resolution(1080)


class TestResolutionFactoryMethods:
    """Tests for Resolution factory methods."""

    def test_unknown_factory_should_create_unknown_resolution(self):
        from src.domain.media.value_objects import Resolution

        resolution = Resolution.unknown()

        assert resolution.value == "Unknown"


class TestResolutionProperties:
    """Tests for Resolution computed properties."""

    def test_is_sd_should_return_true_for_360p(self):
        from src.domain.media.value_objects import Resolution

        resolution = Resolution("360p")

        assert resolution.is_sd is True

    def test_is_sd_should_return_true_for_480p(self):
        from src.domain.media.value_objects import Resolution

        resolution = Resolution("480p")

        assert resolution.is_sd is True

    def test_is_sd_should_return_false_for_720p(self):
        from src.domain.media.value_objects import Resolution

        resolution = Resolution("720p")

        assert resolution.is_sd is False

    def test_is_sd_should_return_false_for_unknown(self):
        from src.domain.media.value_objects import Resolution

        resolution = Resolution("Unknown")

        assert resolution.is_sd is False

    def test_is_hd_should_return_true_for_720p(self):
        from src.domain.media.value_objects import Resolution

        resolution = Resolution("720p")

        assert resolution.is_hd is True

    def test_is_hd_should_return_true_for_1080p(self):
        from src.domain.media.value_objects import Resolution

        resolution = Resolution("1080p")

        assert resolution.is_hd is True

    def test_is_hd_should_return_true_for_2k(self):
        from src.domain.media.value_objects import Resolution

        resolution = Resolution("2K")

        assert resolution.is_hd is True

    def test_is_hd_should_return_true_for_4k(self):
        from src.domain.media.value_objects import Resolution

        resolution = Resolution("4K")

        assert resolution.is_hd is True

    def test_is_hd_should_return_false_for_360p(self):
        from src.domain.media.value_objects import Resolution

        resolution = Resolution("360p")

        assert resolution.is_hd is False

    def test_is_hd_should_return_false_for_480p(self):
        from src.domain.media.value_objects import Resolution

        resolution = Resolution("480p")

        assert resolution.is_hd is False

    def test_is_hd_should_return_false_for_unknown(self):
        from src.domain.media.value_objects import Resolution

        resolution = Resolution("Unknown")

        assert resolution.is_hd is False

    def test_is_4k_should_return_true_for_4k(self):
        from src.domain.media.value_objects import Resolution

        resolution = Resolution("4K")

        assert resolution.is_4k is True

    def test_is_4k_should_return_false_for_1080p(self):
        from src.domain.media.value_objects import Resolution

        resolution = Resolution("1080p")

        assert resolution.is_4k is False


class TestResolutionEquality:
    """Tests for Resolution equality and hashing."""

    def test_should_be_equal_when_same_value(self):
        from src.domain.media.value_objects import Resolution

        res1 = Resolution("1080p")
        res2 = Resolution("1080p")

        assert res1 == res2

    def test_should_not_be_equal_when_different_value(self):
        from src.domain.media.value_objects import Resolution

        res1 = Resolution("1080p")
        res2 = Resolution("4K")

        assert res1 != res2

    def test_should_be_hashable(self):
        from src.domain.media.value_objects import Resolution

        resolution = Resolution("1080p")

        resolution_set = {resolution}

        assert resolution in resolution_set


class TestResolutionStringRepresentation:
    """Tests for Resolution string conversion."""

    def test_should_convert_to_string(self):
        from src.domain.media.value_objects import Resolution

        resolution = Resolution("1080p")

        assert str(resolution) == "1080p"

    def test_should_have_descriptive_repr(self):
        from src.domain.media.value_objects import Resolution

        resolution = Resolution("1080p")

        assert repr(resolution) == "Resolution('1080p')"


class TestResolutionImmutability:
    """Tests for Resolution immutability."""

    def test_should_be_immutable(self):
        from src.domain.media.value_objects import Resolution

        resolution = Resolution("1080p")

        with pytest.raises(DomainValidationException):
            resolution.root = "4K"
