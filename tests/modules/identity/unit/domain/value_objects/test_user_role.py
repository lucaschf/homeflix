"""Tests for UserRole enumeration."""

import pytest

from src.modules.identity.domain.value_objects.user_role import UserRole


class TestUserRole:
    def test_should_have_admin_member_values(self):
        assert UserRole.ADMIN.value == "admin"
        assert UserRole.MEMBER.value == "member"

    def test_should_construct_from_string(self):
        assert UserRole("admin") is UserRole.ADMIN
        assert UserRole("member") is UserRole.MEMBER

    def test_should_reject_unknown_value(self):
        with pytest.raises(ValueError, match="not a valid"):
            UserRole("superhero")

    def test_should_serialize_as_string(self):
        # StrEnum subclasses behave as str — important for SQLAlchemy storage
        assert str(UserRole.ADMIN) == "admin"
        assert UserRole.MEMBER == "member"
