"""Tests for UserId value object."""

import pytest

from src.building_blocks.domain.errors import DomainValidationException
from src.shared_kernel.value_objects.user_id import UserId


class TestUserIdCreation:
    def test_should_accept_well_formed_id(self):
        user_id = UserId("usr_2xK9mPqR7nL4")

        assert user_id.value == "usr_2xK9mPqR7nL4"
        assert user_id.prefix == "usr"

    def test_should_generate_a_new_id_with_correct_prefix(self):
        user_id = UserId.generate()

        assert user_id.prefix == "usr"
        assert len(user_id.random_part) == 12

    def test_generated_ids_should_be_unique(self):
        a = UserId.generate()
        b = UserId.generate()

        assert a != b


class TestUserIdValidation:
    def test_should_reject_wrong_prefix(self):
        with pytest.raises(DomainValidationException, match="must have 'usr' prefix"):
            UserId("mov_2xK9mPqR7nL4")

    def test_should_reject_missing_underscore(self):
        with pytest.raises(DomainValidationException, match="underscore separator"):
            UserId("usr2xK9mPqR7nL4")

    def test_should_reject_random_part_with_wrong_length(self):
        with pytest.raises(DomainValidationException, match="must be 12 characters"):
            UserId("usr_short")

    def test_should_reject_non_string(self):
        with pytest.raises(DomainValidationException):
            UserId(12345)  # type: ignore[arg-type]


class TestUserIdEquality:
    def test_same_value_should_be_equal(self):
        a = UserId("usr_2xK9mPqR7nL4")
        b = UserId("usr_2xK9mPqR7nL4")

        assert a == b
        assert hash(a) == hash(b)

    def test_different_value_should_not_be_equal(self):
        a = UserId.generate()
        b = UserId.generate()

        assert a != b
