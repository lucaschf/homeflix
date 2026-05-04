"""WatchlistItem ORM model."""

from datetime import datetime

from sqlalchemy import DateTime, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.persistence.base import Base


class WatchlistItemModel(Base):
    """SQLAlchemy model for WatchlistItem.

    Maps to the 'watchlist_items' table. One row per (profile, media) —
    different profiles in the same household keep their own watchlists.

    ``profile_id`` is stored as the prefixed external ID; cross-BC
    references are strings, not UUIDs (per ADR-008).
    """

    __table_args__ = (
        UniqueConstraint(
            "profile_id",
            "media_id",
            name="uq_watchlist_items_profile_media",
        ),
    )

    profile_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    media_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    media_type: Mapped[str] = mapped_column(String(20), nullable=False)
    added_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    def __repr__(self) -> str:
        """Return string representation."""
        return (
            f"<WatchlistItemModel(id={self.id}, profile_id={self.profile_id!r}, "
            f"media_id={self.media_id!r}, media_type={self.media_type!r})>"
        )


__all__ = ["WatchlistItemModel"]
