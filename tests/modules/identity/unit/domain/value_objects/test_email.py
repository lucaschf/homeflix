"""Tests for Email value object."""

import pytest

from src.building_blocks.domain.errors import DomainValidationException
from src.modules.identity.domain.value_objects.email import Email


class TestEmailCreation:
    def test_should_accept_simple_email(self):
        email = Email("user@example.com")

        assert email.value == "user@example.com"

    def test_should_lowercase_domain(self):
        email = Email("user@EXAMPLE.COM")

        assert email.value == "user@example.com"

    def test_should_lowercase_local_part(self):
        email = Email("USER@example.com")

        assert email.value == "user@example.com"

    def test_should_strip_surrounding_whitespace(self):
        email = Email("  user@example.com  ")

        assert email.value == "user@example.com"

    def test_should_accept_subdomains(self):
        email = Email("user@mail.example.co.uk")

        assert email.value == "user@mail.example.co.uk"

    def test_should_accept_plus_addressing(self):
        email = Email("user+tag@example.com")

        assert email.value == "user+tag@example.com"


class TestEmailValidation:
    def test_should_reject_empty_string(self):
        with pytest.raises(DomainValidationException, match="cannot be empty"):
            Email("")

    def test_should_reject_whitespace_only(self):
        with pytest.raises(DomainValidationException, match="cannot be empty"):
            Email("   ")

    def test_should_reject_missing_at_sign(self):
        with pytest.raises(DomainValidationException, match="valid format"):
            Email("userexample.com")

    def test_should_reject_missing_domain_dot(self):
        with pytest.raises(DomainValidationException, match="valid format"):
            Email("user@example")

    def test_should_reject_missing_local_part(self):
        with pytest.raises(DomainValidationException, match="valid format"):
            Email("@example.com")

    def test_should_accept_email_at_max_length(self):
        # 314 'a' chars + '@x.com' (6 chars) = 320 chars total — MAX_LENGTH boundary
        boundary_email = "a" * 314 + "@x.com"

        email = Email(boundary_email)

        assert email.value == boundary_email

    def test_should_reject_email_exceeding_max_length(self):
        # 315 + 6 = 321 chars → 1 over MAX_LENGTH
        too_long = "a" * 315 + "@x.com"

        with pytest.raises(DomainValidationException, match="cannot exceed 320"):
            Email(too_long)


class TestEmailEquality:
    def test_same_value_should_be_equal(self):
        a = Email("user@example.com")
        b = Email("USER@EXAMPLE.COM")

        assert a == b
        assert hash(a) == hash(b)

    def test_different_value_should_not_be_equal(self):
        a = Email("alice@example.com")
        b = Email("bob@example.com")

        assert a != b
