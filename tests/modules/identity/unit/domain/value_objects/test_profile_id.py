"""Tests for ProfileId value object."""

import pytest

from src.building_blocks.domain.errors import DomainValidationException
from src.shared_kernel.value_objects.profile_id import ProfileId


class TestProfileIdCreation:
    def test_should_accept_well_formed_id(self):
        profile_id = ProfileId("prf_2xK9mPqR7nL4")

        assert profile_id.value == "prf_2xK9mPqR7nL4"
        assert profile_id.prefix == "prf"

    def test_should_generate_a_new_id_with_correct_prefix(self):
        profile_id = ProfileId.generate()

        assert profile_id.prefix == "prf"
        assert len(profile_id.random_part) == 12


class TestProfileIdValidation:
    def test_should_reject_wrong_prefix(self):
        with pytest.raises(DomainValidationException, match="must have 'prf' prefix"):
            ProfileId("usr_2xK9mPqR7nL4")

    def test_should_reject_invalid_format(self):
        with pytest.raises(DomainValidationException, match="must be 12 characters"):
            ProfileId("prf_xx")

    def test_should_reject_non_string(self):
        with pytest.raises(DomainValidationException):
            ProfileId(12345)  # type: ignore[arg-type]


class TestProfileIdEquality:
    def test_same_value_should_be_equal(self):
        a = ProfileId("prf_2xK9mPqR7nL4")
        b = ProfileId("prf_2xK9mPqR7nL4")

        assert a == b
        assert hash(a) == hash(b)

    def test_different_value_should_not_be_equal(self):
        a = ProfileId("prf_2xK9mPqR7nL4")
        b = ProfileId("prf_9yZ8xWvU3tS1")

        assert a != b

    def test_independently_generated_ids_should_not_be_equal(self):
        a = ProfileId.generate()
        b = ProfileId.generate()

        assert a != b
