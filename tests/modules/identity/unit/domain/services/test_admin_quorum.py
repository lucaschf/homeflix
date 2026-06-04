"""Tests for the ``AdminQuorum`` domain service."""

import pytest

from src.modules.identity.domain.entities.user import User
from src.modules.identity.domain.errors import CannotDemoteLastAdminError
from src.modules.identity.domain.services import AdminQuorum
from src.modules.identity.domain.value_objects.email import Email
from src.modules.identity.domain.value_objects.user_role import UserRole


def _user(role: UserRole) -> User:
    return User.create(email=Email("admin@homeflix.local"), role=role)


@pytest.mark.unit
class TestAdminQuorum:
    """The guard refuses to strip the last active admin (ADR-017)."""

    def test_raises_when_admin_is_the_last_one(self) -> None:
        with pytest.raises(CannotDemoteLastAdminError):
            AdminQuorum.ensure_can_remove_admin(_user(UserRole.ADMIN), active_admin_count=1)

    def test_allows_when_other_admins_remain(self) -> None:
        AdminQuorum.ensure_can_remove_admin(_user(UserRole.ADMIN), active_admin_count=2)

    def test_no_op_for_non_admin(self) -> None:
        # A member never threatens the quorum, even at count 0.
        AdminQuorum.ensure_can_remove_admin(_user(UserRole.MEMBER), active_admin_count=0)
