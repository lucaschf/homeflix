"""Unit tests for UserMapper's parental_pin_hash handling (ADR-035).

The repository round trip lives in the integration suite; these pin the
mapper details that fail silently: ``update_model`` must leave the column
alone (a stale entity would otherwise overwrite a PIN changed meanwhile),
and ``to_entity`` must not decode a stored value to "no PIN".
"""

import uuid

import pytest

from src.modules.identity.domain.entities.user import User
from src.modules.identity.domain.value_objects.email import Email
from src.modules.identity.infrastructure.persistence.mappers.user_mapper import UserMapper
from src.modules.identity.infrastructure.persistence.models.user_model import UserModel
from src.shared_kernel.value_objects.user_id import UserId

pytestmark = pytest.mark.unit


def _model(parental_pin_hash: str | None) -> UserModel:
    return UserModel(
        id=uuid.uuid4(),
        external_id="usr_mapper000001",
        email="parent@example.com",
        hashed_password="$argon2id$password",
        is_active=True,
        is_superuser=False,
        is_verified=True,
        role="member",
        parental_pin_hash=parental_pin_hash,
    )


class TestUserMapperParentalPin:
    @pytest.mark.parametrize("stored", [None, "$argon2id$pin", ""])
    def test_to_entity_should_read_the_column_as_stored(self, stored: str | None) -> None:
        # ``""`` never reaches the table (CHECK), but decoding it to
        # ``None`` — the ``hashed_password or None`` idiom — would read a
        # configured PIN as "no PIN".
        entity = UserMapper.to_entity(_model(stored))

        assert entity.parental_pin_hash == stored

    def test_to_model_should_write_the_column(self) -> None:
        entity = User(
            id=UserId("usr_mapper000001"),
            email=Email("parent@example.com"),
            parental_pin_hash="$argon2id$pin",
        )

        assert UserMapper.to_model(entity).parental_pin_hash == "$argon2id$pin"

    @pytest.mark.parametrize(
        ("stored", "entity_value"), [("$argon2id$pin", None), (None, "$argon2id$pin")]
    )
    def test_update_model_should_leave_the_column_untouched(
        self, stored: str | None, entity_value: str | None
    ) -> None:
        # Only ``set_parental_pin_hash`` writes an existing user's PIN hash.
        # A stale entity read before a PIN was set must not clear it.
        model = _model(stored)
        entity = UserMapper.to_entity(model).with_updates(parental_pin_hash=entity_value)

        UserMapper.update_model(model, entity)

        assert model.parental_pin_hash == stored
