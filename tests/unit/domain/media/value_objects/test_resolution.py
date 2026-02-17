"""Tests for Resolution value object."""

import pytest

from src.domain.shared.exceptions.domain import DomainValidationException


class TestResolutionCreation:
    """Tests for Resolution instantiation."""

    def test_should_create_with_360p(self):
        from src.domain.media.value_objects import Resolution

        resolution = Resolution("360p")

        assert resolution.value == "360p"
        assert resolution.width == 640
        assert resolution.height == 360

    def test_should_create_with_480p(self):
        from src.domain.media.value_objects import Resolution

        resolution = Resolution("480p")

        assert resolution.value == "480p"
        assert resolution.width == 854
        assert resolution.height == 480

    def test_should_create_with_720p(self):
        from src.domain.media.value_objects import Resolution

        resolution = Resolution("720p")

        assert resolution.value == "720p"
        assert resolution.width == 1280
        assert resolution.height == 720

    def test_should_create_with_1080p(self):
        from src.domain.media.value_objects import Resolution

        resolution = Resolution("1080p")

        assert resolution.value == "1080p"
        assert resolution.width == 1920
        assert resolution.height == 1080

    def test_should_create_with_2k(self):
        from src.domain.media.value_objects import Resolution

        resolution = Resolution("2K")

        assert resolution.value == "2K"
        assert resolution.width == 2560
        assert resolution.height == 1440

    def test_should_create_with_4k(self):
        from src.domain.media.value_objects import Resolution

        resolution = Resolution("4K")

        assert resolution.value == "4K"
        assert resolution.width == 3840
        assert resolution.height == 2160

    def test_should_create_with_unknown(self):
        from src.domain.media.value_objects import Resolution

        resolution = Resolution("Unknown")

        assert resolution.value == "Unknown"
        assert resolution.width == 0
        assert resolution.height == 0

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

        with pytest.raises((DomainValidationException, ValueError)):
            Resolution(1080)


class TestResolutionFactoryMethods:
    """Tests for Resolution factory methods."""

    def test_unknown_factory_should_create_unknown_resolution(self):
        from src.domain.media.value_objects import Resolution

        resolution = Resolution.unknown()

        assert resolution.value == "Unknown"

    def test_from_name_should_create_resolution(self):
        from src.domain.media.value_objects import Resolution

        resolution = Resolution.from_name("4K")

        assert resolution.value == "4K"
        assert resolution.width == 3840


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


class TestResolutionPixels:
    """Tests for Resolution pixel computations."""

    def test_total_pixels_for_1080p(self):
        from src.domain.media.value_objects import Resolution

        resolution = Resolution("1080p")

        assert resolution.total_pixels == 1920 * 1080

    def test_total_pixels_for_4k(self):
        from src.domain.media.value_objects import Resolution

        resolution = Resolution("4K")

        assert resolution.total_pixels == 3840 * 2160

    def test_total_pixels_for_unknown(self):
        from src.domain.media.value_objects import Resolution

        resolution = Resolution("Unknown")

        assert resolution.total_pixels == 0


class TestResolutionComparison:
    """Tests for Resolution comparison operators."""

    def test_4k_should_be_greater_than_1080p(self):
        from src.domain.media.value_objects import Resolution

        assert Resolution("4K") > Resolution("1080p")

    def test_720p_should_be_less_than_1080p(self):
        from src.domain.media.value_objects import Resolution

        assert Resolution("720p") < Resolution("1080p")

    def test_same_resolution_should_be_ge_and_le(self):
        from src.domain.media.value_objects import Resolution

        r1 = Resolution("1080p")
        r2 = Resolution("1080p")

        assert r1 >= r2
        assert r1 <= r2

    def test_all_resolutions_sort_correctly(self):
        from src.domain.media.value_objects import Resolution

        resolutions = [
            Resolution("4K"),
            Resolution("360p"),
            Resolution("1080p"),
            Resolution("720p"),
            Resolution("480p"),
            Resolution("2K"),
        ]

        sorted_res = sorted(resolutions)

        assert [r.name for r in sorted_res] == [
            "360p",
            "480p",
            "720p",
            "1080p",
            "2K",
            "4K",
        ]


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
            resolution.name = "4K"  # type: ignore[misc]


class TestResolutionPydanticFieldValidation:
    """Tests that Resolution works as a Pydantic field with string input."""

    def test_string_input_in_pydantic_model(self):
        from src.domain.media.entities import Movie

        movie = Movie.create(
            title="Test",
            year=2024,
            duration=7200,
            file_path="/movies/test.mkv",
            file_size=1_000_000_000,
            resolution="1080p",
        )

        assert movie.resolution.name == "1080p"
        assert movie.resolution.width == 1920
