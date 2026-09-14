"""User SQLAlchemy ORM model.

Combines ``BaseWithUUID`` (project conventions: ``external_id``,
timestamps, soft-delete, snake_case ``__tablename__`` from
``_CommonColumnsMixin``) with FastAPI Users' ``SQLAlchemyBaseUserTableUUID``
(UUID primary key, ``email``, ``hashed_password``, ``is_active``,
``is_superuser``, ``is_verified``).

The internal database PK is the UUID — that's what FastAPI Users
operates on. ``external_id`` (``usr_xxxxxxxxxxxx``) is what every other
layer (domain, application, presentation) sees, so the API never leaks
UUIDs (preserves ADR-002). Translation happens in ``UserMapper``.
"""

from fastapi_users_db_sqlalchemy import SQLAlchemyBaseUserTableUUID
from sqlalchemy import CheckConstraint, String
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.persistence.base import BaseWithUUID


class UserModel(BaseWithUUID, SQLAlchemyBaseUserTableUUID):
    """SQLAlchemy model for the ``User`` aggregate.

    Inherited from ``BaseWithUUID`` (via ``_CommonColumnsMixin``):
        - ``external_id``, ``created_at``, ``updated_at``, ``deleted_at``
        - Soft-delete helpers (``is_deleted``, ``soft_delete``, ``restore``)

    Inherited from ``SQLAlchemyBaseUserTableUUID``:
        - ``id`` (UUID primary key, default ``uuid.uuid4``)
        - ``email`` (String(320), unique, indexed)
        - ``hashed_password`` (String(1024))
        - ``is_active``, ``is_superuser``, ``is_verified`` (Boolean)

    Attributes:
        role: One of ``admin`` / ``member`` (``UserRole`` enum). Stored
            as a plain string for flexibility — the domain VO converts
            it back to the enum.
        parental_pin_hash: Hash of the household's parental PIN, or NULL
            when none is configured (ADR-035). An empty string is refused
            by the CHECK so it can never stand in for "no PIN".
    """

    __tablename__ = "users"

    role: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="member",
        index=True,
    )
    # Column-level CHECK, as the migration adds it: SQLite can only drop
    # a column whose CHECK belongs to that column.
    parental_pin_hash: Mapped[str | None] = mapped_column(
        String(1024),
        CheckConstraint(
            "parental_pin_hash IS NULL OR length(parental_pin_hash) > 0",
            name="ck_users_parental_pin_hash_not_empty",
        ),
        nullable=True,
    )


__all__ = ["UserModel"]
