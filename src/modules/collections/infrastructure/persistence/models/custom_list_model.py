"""CustomList and CustomListItem ORM models."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.persistence.base import Base


class CustomListModel(Base):
    """SQLAlchemy model for CustomList.

    Maps to the 'custom_lists' table. One row per (profile, list).

    ``profile_id`` is stored as the prefixed external ID (``prf_xxx``)
    so every list query can scope by profile without joining ``profiles``.
    Cross-BC references travel as strings, not UUIDs (per ADR-008).
    """

    profile_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    item_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    items: Mapped[list["CustomListItemModel"]] = relationship(
        back_populates="custom_list",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        """Return string representation."""
        return (
            f"<CustomListModel(id={self.id}, profile_id={self.profile_id!r}, "
            f"name={self.name!r}, item_count={self.item_count})>"
        )


class CustomListItemModel(Base):
    """SQLAlchemy model for CustomListItem.

    Maps to the 'custom_list_items' table. One row per item in a list.

    Items inherit profile scoping from their parent ``CustomListModel``
    via the ``custom_list_id`` FK; the repository joins on the parent
    to enforce per-profile isolation rather than denormalising
    ``profile_id`` here.
    """

    custom_list_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("custom_lists.id"),
        nullable=False,
        index=True,
    )
    media_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    media_type: Mapped[str] = mapped_column(String(20), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    added_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    custom_list: Mapped[CustomListModel] = relationship(back_populates="items")

    def __repr__(self) -> str:
        """Return string representation."""
        return (
            f"<CustomListItemModel(id={self.id}, media_id={self.media_id!r}, "
            f"position={self.position})>"
        )


__all__ = ["CustomListItemModel", "CustomListModel"]
