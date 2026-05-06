"""SQLAlchemy base classes for ORM models.

Three bases coexist, all sharing the same metadata so a single
``target_metadata = Base.metadata`` in ``migrations/env.py`` discovers
every table:

- ``Base`` — default base for tables with autoincrement integer PK plus
  the standard ``external_id`` + timestamps + soft-delete columns.
  Used by every existing module (media, library, collections, etc.).
- ``BaseWithUUID`` — base for tables whose PK is a UUID. Concrete
  subclasses declare their own ``id`` column. Used by the identity
  bounded context (``users``, ``profiles``) where FastAPI Users
  requires UUID primary keys.
- ``BaseSecret`` — minimal base for tables that store opaque secrets
  (e.g., ``access_tokens``). No ``id``, ``external_id``, or soft-delete:
  the secret is the PK, it is never exposed via API, and revocation is
  hard ``DELETE`` per ADR-011.

The shared columns and helpers live in ``_CommonColumnsMixin`` so the
two "regular" bases (``Base`` and ``BaseWithUUID``) stay in sync.
"""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column


class _CommonColumnsMixin:
    """Mixin contributing the standard external_id + timestamps + soft-delete.

    Pulled out of ``Base`` so ``BaseWithUUID`` can reuse the same columns
    without inheriting the integer PK.
    """

    @declared_attr.directive
    @classmethod
    def __tablename__(cls) -> str:
        """Generate snake_case, pluralized table name from the class name.

        ``MovieModel`` -> ``movies``; ``SeriesModel`` -> ``series``;
        ``CategoryModel`` -> ``categories``.
        """
        name = cls.__name__
        if name.endswith("Model"):
            name = name[:-5]

        result: list[str] = []
        for i, char in enumerate(name):
            if char.isupper() and i > 0:
                result.append("_")
            result.append(char.lower())

        table_name = "".join(result)

        if table_name.endswith("s"):
            return table_name
        if table_name.endswith("y"):
            return f"{table_name[:-1]}ies"
        return f"{table_name}s"

    external_id: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
        index=True,
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
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
        index=True,
    )

    @property
    def is_deleted(self) -> bool:
        """Check if the record has been softly deleted."""
        return self.deleted_at is not None

    def soft_delete(self) -> None:
        """Mark the record as deleted."""
        self.deleted_at = datetime.now(UTC)

    def restore(self) -> None:
        """Restore a soft deleted record."""
        self.deleted_at = None

    def __repr__(self) -> str:
        """Return string representation with key fields."""
        identifier = getattr(self, "id", "?")
        external = getattr(self, "external_id", "?")
        return f"<{self.__class__.__name__}(id={identifier}, external_id={external!r})>"

    def to_dict(self) -> dict[str, Any]:
        """Convert model to dictionary."""
        return {c.name: getattr(self, c.name) for c in self.__table__.columns.values()}  # type: ignore[attr-defined]


class Base(DeclarativeBase, _CommonColumnsMixin):
    """Default base for ORM models with autoincrement integer PK.

    Provides:
        - Auto-generated table name from class name
        - Common ``id`` (int autoincrement), ``external_id``,
          ``created_at``, ``updated_at``, ``deleted_at`` columns
        - ``soft_delete``/``restore`` helpers and ``is_deleted`` property
        - ``to_dict`` and ``__repr__``

    Example:
        >>> class MovieModel(Base):
        ...     title: Mapped[str] = mapped_column(String(500))
    """

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)


class BaseWithUUID(DeclarativeBase, _CommonColumnsMixin):
    """Base for ORM models whose primary key is a UUID.

    Concrete subclasses MUST declare their own ``id: Mapped[UUID]`` column
    (typically using ``fastapi_users_db_sqlalchemy.GUID`` for
    cross-dialect portability). This base intentionally does not declare
    ``id`` so that subclasses combining ``BaseWithUUID`` with FastAPI
    Users mixins (``SQLAlchemyBaseUserTable[UUID]``) — which contribute
    their own ``id`` column — have no MRO conflict.

    Shares ``Base.metadata`` so a single alembic ``target_metadata``
    discovers tables from both bases.

    Example:
        >>> class ProfileModel(BaseWithUUID):
        ...     id: Mapped[UUID] = mapped_column(GUID, primary_key=True, default=uuid4)
        ...     name: Mapped[str] = mapped_column(String(50))
    """

    metadata = Base.metadata
    __abstract__ = True


class BaseSecret(DeclarativeBase):
    """Minimal base for tables holding opaque secrets (e.g., session tokens).

    Used only by ``AccessTokenModel`` in the identity BC. Provides nothing
    beyond ``DeclarativeBase`` — no ``id``, no ``external_id``, no
    timestamps, no soft-delete:

    - The secret value is the primary key (provided by the FastAPI Users
      access-token mixin), so an autoincrement ``id`` would be redundant.
    - The secret must never appear in logs or API responses, so the
      ``external_id`` convention from ADR-002 does not apply.
    - Revocation is hard ``DELETE`` per ADR-011 (logout, kill switch),
      so soft-delete is the wrong semantic.

    Shares ``Base.metadata`` so alembic discovers the table.
    """

    metadata = Base.metadata
    __abstract__ = True


__all__ = ["Base", "BaseSecret", "BaseWithUUID"]
