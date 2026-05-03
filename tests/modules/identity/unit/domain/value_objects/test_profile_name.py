"""Tests for ProfileName value object."""

import pytest

from src.building_blocks.domain.errors import DomainValidationException
from src.modules.identity.domain.value_objects.profile_name import ProfileName


class TestProfileNameCreation:
    def test_should_accept_simple_name(self):
        name = ProfileName("Lucas")

        assert name.value == "Lucas"

    def test_should_strip_surrounding_whitespace(self):
        name = ProfileName("  Kids  ")

        assert name.value == "Kids"

    def test_should_accept_single_character(self):
        name = ProfileName("L")

        assert name.value == "L"

    def test_should_accept_max_length(self):
        long_name = "A" * 50

        name = ProfileName(long_name)

        assert len(name.value) == 50


class TestProfileNameValidation:
    def test_should_reject_empty(self):
        with pytest.raises(DomainValidationException, match="cannot be empty"):
            ProfileName("")

    def test_should_reject_whitespace_only(self):
        with pytest.raises(DomainValidationException, match="cannot be empty"):
            ProfileName("   ")

    def test_should_reject_exceeding_max_length(self):
        with pytest.raises(DomainValidationException, match="cannot exceed 50"):
            ProfileName("A" * 51)


class TestProfileNameEquality:
    def test_same_name_should_be_equal(self):
        a = ProfileName("Kids")
        b = ProfileName("Kids")

        assert a == b
        assert hash(a) == hash(b)
