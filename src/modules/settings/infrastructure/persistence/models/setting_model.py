"""SettingModel — ORM mapping for ``app_settings``.

ADR-013 chose a single-table key/value-JSON schema where the
primary key is the semantic :class:`SettingKey` string. The table
deliberately omits the conventions baked into ``Base`` (surrogate
integer id, ``external_id``, soft-delete) — the semantic key is
the identity and rows are upserted or absent, never archived.

Precedent for diverging from ``Base``: ``BaseSecret`` (identity BC).
``BaseSecret`` is named for its primary use (opaque session tokens),
so we declare our own minimal :class:`_SettingsBase` here rather
than overload its semantics.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from src.infrastructure.persistence.base import Base


class _SettingsBase(DeclarativeBase):
    """Minimal declarative base shared with ``Base.metadata``.

    Mirrors the ``BaseSecret`` shape: no surrogate id, no
    ``external_id``, no soft-delete, just a declarative root pinned
    to the project-wide metadata so alembic discovers it.
    """

    metadata = Base.metadata
    __abstract__ = True


class SettingModel(_SettingsBase):
    """SQLAlchemy model for the ``app_settings`` table.

    Each row stores one serialized configuration Value Object.

    Attributes:
        key: Semantic identifier matching a :class:`SettingKey`
            enum value (``"scheduler"``, ``"intro_detection"``, ...).
            Acts as the natural primary key.
        value_json: JSON-serialized VO payload. Deserialized back
            into the matching :class:`ConfigVO` subtype by
            :class:`SettingMapper`.
        source: Provenance — ``"migration_seed"``, ``"admin"``, or
            ``"sql_override"``. Mirrors
            :class:`SettingSource`.
        updated_by_user_id: External id (``usr_xxx``) of the user
            that last edited this row via the admin panel. ``NULL``
            for migration-seeded rows.
    """

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(50), primary_key=True)
    value_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    source: Mapped[str] = mapped_column(String(30), nullable=False)
    updated_by_user_id: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        """Return string representation."""
        return (
            f"<SettingModel(key={self.key!r}, source={self.source!r}, "
            f"updated_at={self.updated_at!r})>"
        )


__all__ = ["SettingModel"]
