"""Tests for the UserRead projection.

Locks ADR-002 enforcement at the API surface: the database UUID is
the internal primary key but must NEVER be exposed as ``id`` to API
clients — they see only the prefixed ``external_id``.
"""

import uuid

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

        projected = UserRead.from_model(model)

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

        projected = UserRead.from_model(model)

        assert projected.email == "user@example.com"
        assert projected.role == "member"
        assert projected.is_active is False
        assert projected.is_verified is True
