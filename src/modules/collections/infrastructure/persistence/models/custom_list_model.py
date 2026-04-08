"""CustomList and CustomListItem ORM models."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.config.persistence.base import Base


class CustomListModel(Base):
    """SQLAlchemy model for CustomList.

    Maps to the 'custom_lists' table. One row per user-created list.

    Attributes:
        name: Display name of the list.
        item_count: Number of items in the list.
        items: Relationship to CustomListItemModel.
    """

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
            f"<CustomListModel(id={self.id}, name={self.name!r}, " f"item_count={self.item_count})>"
        )


class CustomListItemModel(Base):
    """SQLAlchemy model for CustomListItem.

    Maps to the 'custom_list_items' table. One row per item in a list.

    Attributes:
        custom_list_id: Foreign key to the parent custom list (internal ID).
        media_id: External ID of the media (mov_xxx or ser_xxx).
        media_type: Type of media ("movie" or "series").
        position: Ordering position within the list.
        added_at: Timestamp when the item was added.
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
