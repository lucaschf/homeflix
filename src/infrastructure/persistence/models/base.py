"""SQLAlchemy base model with common fields and mixins.

All ORM models should inherit from Base.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models.

    Provides:
        - Auto-generated table name from class name
        - Common id, external_id, created_at, updated_at columns
        - Repr helper

    Example:
        >>> class MovieModel(Base):
        ...     title: Mapped[str] = mapped_column(String(500))
    """

    # Use snake_case table names derived from class name
    @declared_attr.directive
    @classmethod
    def __tablename__(cls) -> str:
        """Generate table name from class name.

        MovieModel -> movies
        SeriesModel -> series
        """
        name = cls.__name__
        if name.endswith("Model"):
            name = name[:-5]  # Remove "Model" suffix

        # Convert CamelCase to snake_case
        result: list[str] = []
        for i, char in enumerate(name):
            if char.isupper() and i > 0:
                result.append("_")
            result.append(char.lower())

        table_name = "".join(result)

        # Pluralize (simple rules)
        if table_name.endswith("s"):
            return table_name  # series -> series
        if table_name.endswith("y"):
            return table_name[:-1] + "ies"  # category -> categories
        return table_name + "s"  # movie -> movies

    # Primary key (internal, never exposed via API)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # External ID (exposed via API, prefixed: mov_xxx, ser_xxx, etc.)
    external_id: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
        index=True,
    )

    # Timestamps
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

    # Soft delete
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
        index=True,
    )

    @property
    def is_deleted(self) -> bool:
        """Check if the record has been soft deleted."""
        return self.deleted_at is not None

    def soft_delete(self) -> None:
        """Mark the record as deleted."""
        self.deleted_at = datetime.now()

    def restore(self) -> None:
        """Restore a soft deleted record."""
        self.deleted_at = None

    def __repr__(self) -> str:
        """Return string representation with key fields."""
        return f"<{self.__class__.__name__}(id={self.id}, external_id={self.external_id!r})>"

    def to_dict(self) -> dict[str, Any]:
        """Convert model to dictionary.

        Returns:
            Dictionary with column values.
        """
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


__all__ = ["Base"]
