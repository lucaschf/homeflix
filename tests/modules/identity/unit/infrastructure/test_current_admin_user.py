"""Unit tests for the ``current_admin_user`` FastAPI dependency."""

import uuid

import pytest

from src.building_blocks.application.errors import ForbiddenOperationException
from src.modules.identity.domain.value_objects.user_role import UserRole
from src.modules.identity.infrastructure.auth.fastapi_users import current_admin_user
from src.modules.identity.infrastructure.persistence.models.user_model import UserModel


def _make_user(role: str) -> UserModel:
    """Build a minimal ``UserModel`` for the dep call.

    Only attributes the dep actually inspects are set — the rest of
    the SQLAlchemy machinery (PK, hashed password, timestamps) is
    irrelevant here; ``current_admin_user`` only reads ``role``.
    """
    user = UserModel()
    user.id = uuid.uuid4()
    user.external_id = "usr_test"
    user.email = "user@example.com"
    user.hashed_password = "x"
    user.is_active = True
    user.is_superuser = role == UserRole.ADMIN.value
    user.is_verified = True
    user.role = role
    return user


class TestCurrentAdminUser:
    async def test_should_return_user_when_role_is_admin(self) -> None:
        user = _make_user(UserRole.ADMIN.value)

        result = await current_admin_user(user=user)

        assert result is user

    async def test_should_raise_forbidden_when_role_is_member(self) -> None:
        user = _make_user(UserRole.MEMBER.value)

        with pytest.raises(ForbiddenOperationException) as exc_info:
            await current_admin_user(user=user)

        assert exc_info.value.http_status == 403
        assert exc_info.value.required_permission == "admin"
