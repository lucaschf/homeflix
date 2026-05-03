"""Tests for User aggregate root."""

import pytest

from src.building_blocks.domain.errors import DomainValidationException
from src.modules.identity.domain.entities.user import User
from src.modules.identity.domain.value_objects.email import Email
from src.modules.identity.domain.value_objects.user_id import UserId
from src.modules.identity.domain.value_objects.user_role import UserRole


class TestUserCreate:
    def test_should_create_with_defaults(self):
        user = User.create(email=Email("admin@homeflix.local"))

        assert user.id is None
        assert user.email == Email("admin@homeflix.local")
        assert user.role == UserRole.MEMBER
        assert user.is_active is True
        assert user.is_superuser is False
        assert user.is_verified is False
        assert user.hashed_password is None

    def test_should_create_admin(self):
        user = User.create(
            email=Email("root@homeflix.local"),
            role=UserRole.ADMIN,
            is_superuser=True,
            is_verified=True,
        )

        assert user.role == UserRole.ADMIN
        assert user.is_superuser is True
        assert user.is_verified is True


class TestUserImmutability:
    def test_should_be_frozen(self):
        user = User.create(email=Email("a@b.com"))

        with pytest.raises(DomainValidationException):
            user.role = UserRole.ADMIN  # type: ignore[misc]

    def test_with_role_should_return_new_instance(self):
        original = User.create(email=Email("a@b.com"), role=UserRole.MEMBER)

        promoted = original.with_role(UserRole.ADMIN)

        assert promoted is not original
        assert original.role == UserRole.MEMBER  # original unchanged
        assert promoted.role == UserRole.ADMIN

    def test_with_email_should_return_new_instance(self):
        original = User.create(email=Email("old@b.com"))

        updated = original.with_email(Email("new@b.com"))

        assert updated.email == Email("new@b.com")
        assert original.email == Email("old@b.com")

    def test_deactivated_should_return_inactive_copy(self):
        original = User.create(email=Email("a@b.com"))

        inactive = original.deactivated()

        assert inactive.is_active is False
        assert original.is_active is True

    def test_reactivated_should_return_active_copy(self):
        original = User.create(email=Email("a@b.com")).deactivated()

        reactivated = original.reactivated()

        assert reactivated.is_active is True

    def test_with_verified_should_set_flag(self):
        original = User.create(email=Email("a@b.com"))

        verified = original.with_verified()

        assert verified.is_verified is True


class TestUserEquality:
    def test_users_without_id_should_not_be_equal(self):
        a = User.create(email=Email("a@b.com"))
        b = User.create(email=Email("a@b.com"))

        assert a != b  # entities without id are never equal (different identity)

    def test_users_with_same_id_should_be_equal(self):
        uid = UserId.generate()
        a = User(id=uid, email=Email("a@b.com"))
        b = User(id=uid, email=Email("c@d.com"))

        assert a == b  # equality is by id, not by attributes
