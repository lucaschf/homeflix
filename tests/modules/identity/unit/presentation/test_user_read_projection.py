"""Tests for the UserRead projection.

Locks ADR-002 enforcement at the API surface: the database UUID is
the internal primary key but must NEVER be exposed as ``id`` to API
clients — they see only the prefixed ``external_id``.
"""

import uuid

import pytest

from src.modules.identity.application.dtos.identity_dtos import AdminAccessLevel
from src.modules.identity.infrastructure.persistence.models.user_model import UserModel
from src.modules.identity.presentation.schemas.user_schemas import UserRead


class TestUserReadFromModel:
    def test_id_should_be_the_prefixed_external_id_not_uuid(self):
        # Arrange a model that mirrors what the DB would return after
        # FastAPI Users created the row.
        internal_uuid = uuid.uuid4()
        external = "usr_2xK9mPqR7nL4"
        model = UserModel(
            id=internal_uuid,
            external_id=external,
            email="admin@homeflix.local",
            hashed_password="$argon2id$dummy",
            is_active=True,
            is_superuser=True,
            is_verified=True,
            role="admin",
        )

        projected = UserRead.from_model(model, admin_access=AdminAccessLevel.GRANTED)

        assert projected.id == external
        # And critically: the UUID never makes it into the projection
        assert str(internal_uuid) not in projected.model_dump_json()

    def test_should_carry_email_role_and_flags(self):
        model = UserModel(
            id=uuid.uuid4(),
            external_id="usr_2xK9mPqR7nL4",
            email="user@example.com",
            hashed_password="$argon2id$dummy",
            is_active=False,
            is_superuser=False,
            is_verified=True,
            role="member",
        )

        projected = UserRead.from_model(model, admin_access=AdminAccessLevel.NONE)

        assert projected.email == "user@example.com"
        assert projected.role == "member"
        assert projected.is_active is False
        assert projected.is_verified is True


class TestUserReadParentalPin:
    def _model(self, parental_pin_hash: str | None) -> UserModel:
        return UserModel(
            id=uuid.uuid4(),
            external_id="usr_2xK9mPqR7nL4",
            email="parent@example.com",
            hashed_password="$argon2id$dummy",
            is_active=True,
            is_superuser=False,
            is_verified=True,
            role="member",
            parental_pin_hash=parental_pin_hash,
        )

    def test_should_report_no_pin_when_the_hash_is_null(self):
        projected = UserRead.from_model(self._model(None), admin_access=AdminAccessLevel.NONE)

        assert projected.parental_pin_configured is False

    def test_should_report_a_pin_without_exposing_the_hash(self):
        projected = UserRead.from_model(
            self._model("$argon2id$v=19$pin-hash"), admin_access=AdminAccessLevel.NONE
        )

        assert projected.parental_pin_configured is True
        dumped = projected.model_dump_json()
        assert "pin-hash" not in dumped
        assert "parental_pin_hash" not in dumped


class TestUserReadAdminAccess:
    """``admin_access`` is what the route decided, serialized as its wire value."""

    @pytest.mark.parametrize("access", list(AdminAccessLevel))
    def test_should_carry_the_admin_access_it_is_given(self, access: AdminAccessLevel):
        model = UserModel(
            id=uuid.uuid4(),
            external_id="usr_2xK9mPqR7nL4",
            email="admin@homeflix.local",
            hashed_password="$argon2id$dummy",
            is_active=True,
            is_superuser=True,
            is_verified=True,
            role="admin",
        )

        projected = UserRead.from_model(model, admin_access=access)

        assert projected.model_dump(mode="json")["admin_access"] == access.value
        assert {level.value for level in AdminAccessLevel} == {"none", "granted", "suspended"}

    def test_admin_access_has_no_default(self):
        assert UserRead.model_fields["admin_access"].is_required()
