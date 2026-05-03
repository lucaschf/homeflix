"""Mapper between User domain entity and UserModel ORM model.

The internal database PK is a UUID (FastAPI Users requirement); the
domain only ever sees ``UserId`` (``usr_xxxxxxxxxxxx``). This mapper
is the single point that crosses that boundary — UUID never appears
in any other layer.

On insert the mapper produces a model with all FastAPI Users-managed
fields populated from the entity (``hashed_password``, ``is_verified``,
``is_superuser``). On update, the mapper deliberately writes ONLY the
domain-mutable fields (``role``, ``is_active``); FastAPI Users owns
the password / verification / superuser flow and writes those columns
through ``SQLAlchemyUserDatabase`` instead.
"""

from datetime import UTC, datetime

from src.modules.identity.domain.entities.user import User
from src.modules.identity.domain.value_objects.email import Email
from src.modules.identity.domain.value_objects.user_id import UserId
from src.modules.identity.domain.value_objects.user_role import UserRole
from src.modules.identity.infrastructure.persistence.models.user_model import UserModel


def _ensure_utc(value: datetime | None) -> datetime | None:
    """Attach UTC tzinfo to naive datetimes loaded from the DB.

    Mirrors the helper in ``library_mapper`` — SQLite drops timezone
    info even when the column is declared with ``DateTime(timezone=True)``.
    """
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class UserMapper:
    """Bidirectional mapper for ``User`` ↔ ``UserModel``."""

    @staticmethod
    def to_model(entity: User) -> UserModel:
        """Convert a User entity to a freshly-constructed UserModel.

        Used on insert. Every field is populated from the entity; the
        UUID primary key defaults via the model column (``uuid.uuid4``)
        if not pre-assigned.

        Args:
            entity: The User to persist (must have an id assigned).

        Returns:
            A new ``UserModel`` ready to be added to the session.

        Raises:
            ValueError: If the entity has no id.
        """
        if entity.id is None:
            raise ValueError("Cannot map User entity without ID to model")

        return UserModel(
            external_id=str(entity.id),
            email=entity.email.value,
            hashed_password=entity.hashed_password or "",
            is_active=entity.is_active,
            is_superuser=entity.is_superuser,
            is_verified=entity.is_verified,
            role=entity.role.value,
        )

    @staticmethod
    def to_entity(model: UserModel) -> User:
        """Convert a UserModel back into a User domain entity.

        Args:
            model: The SQLAlchemy model loaded from the session.

        Returns:
            The reconstructed ``User`` with prefixed ``UserId``.
        """
        return User(
            id=UserId(model.external_id),
            email=Email(model.email),
            role=UserRole(model.role),
            is_active=model.is_active,
            is_superuser=model.is_superuser,
            is_verified=model.is_verified,
            hashed_password=model.hashed_password or None,
            created_at=_ensure_utc(model.created_at) or datetime.now(UTC),
            updated_at=_ensure_utc(model.updated_at) or datetime.now(UTC),
        )

    @staticmethod
    def update_model(model: UserModel, entity: User) -> UserModel:
        """Apply ONLY domain-mutable fields onto an existing model.

        Specifically writes ``role`` and ``is_active`` — the columns
        the domain controls. ``hashed_password``, ``is_verified``,
        ``is_superuser`` are intentionally left untouched: FastAPI
        Users owns those via the registration / verification / admin
        flows and updates them through its own database adapter.

        Email is also left untouched here; admin email change is a
        deliberate sensitive flow that isn't in scope for this PR.

        Args:
            model: The existing model to mutate in place.
            entity: The domain entity carrying the new state.

        Returns:
            The same ``model`` reference, mutated.
        """
        model.role = entity.role.value
        model.is_active = entity.is_active
        return model


__all__ = ["UserMapper"]
