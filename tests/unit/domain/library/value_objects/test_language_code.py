"""Tests for LanguageCode value object."""

import pytest

from src.building_blocks.domain.errors import DomainValidationException
from src.shared_kernel.value_objects.language_code import LanguageCode


class TestLanguageCodeCreation:
    """Tests for LanguageCode instantiation."""

    def test_should_create_with_valid_code(self):
        code = LanguageCode("en")

        assert code.value == "en"

    def test_should_normalize_to_lowercase(self):
        code = LanguageCode("EN")

        assert code.value == "en"

    def test_should_trim_whitespace(self):
        code = LanguageCode("  pt  ")

        assert code.value == "pt"

    def test_should_accept_common_codes(self):
        common_codes = ["en", "pt", "es", "fr", "de", "ja", "ko", "zh"]

        for c in common_codes:
            code = LanguageCode(c)
            assert code.value == c


class TestLanguageCodeValidation:
    """Tests for LanguageCode validation."""

    def test_should_raise_error_for_single_character(self):
        with pytest.raises(DomainValidationException, match="ISO 639-1"):
            LanguageCode("e")

    def test_should_raise_error_for_three_characters(self):
        with pytest.raises(DomainValidationException, match="ISO 639-1"):
            LanguageCode("eng")

    def test_should_raise_error_for_numbers(self):
        with pytest.raises(DomainValidationException, match="ISO 639-1"):
            LanguageCode("12")

    def test_should_raise_error_for_empty_string(self):
        with pytest.raises(DomainValidationException, match="ISO 639-1"):
            LanguageCode("")


class TestLanguageCodeFactories:
    """Tests for LanguageCode factory methods."""

    def test_should_create_english(self):
        code = LanguageCode.english()

        assert code.value == "en"

    def test_should_create_portuguese(self):
        code = LanguageCode.portuguese()

        assert code.value == "pt"

    def test_should_create_japanese(self):
        code = LanguageCode.japanese()

        assert code.value == "ja"


class TestLanguageCodeEquality:
    """Tests for LanguageCode equality."""

    def test_same_codes_should_be_equal(self):
        code1 = LanguageCode("en")
        code2 = LanguageCode("en")

        assert code1 == code2

    def test_different_codes_should_not_be_equal(self):
        code1 = LanguageCode("en")
        code2 = LanguageCode("pt")

        assert code1 != code2

    def test_should_be_hashable(self):
        code = LanguageCode("en")

        code_set = {code}

        assert code in code_set
