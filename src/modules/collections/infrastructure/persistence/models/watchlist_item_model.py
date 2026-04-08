"""WatchlistItem ORM model."""

from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from src.config.persistence.base import Base


class WatchlistItemModel(Base):
    """SQLAlchemy model for WatchlistItem.

    Maps to the 'watchlist_items' table. One row per media item.

    Attributes:
        media_id: External ID of the media (mov_xxx or ser_xxx).
        media_type: Type of media ("movie" or "series").
        added_at: Timestamp when the item was added.
    """

    media_id: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, index=True)
    media_type: Mapped[str] = mapped_column(String(20), nullable=False)
    added_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    def __repr__(self) -> str:
        """Return string representation."""
        return (
            f"<WatchlistItemModel(id={self.id}, media_id={self.media_id!r}, "
            f"media_type={self.media_type!r})>"
        )


__all__ = ["WatchlistItemModel"]
