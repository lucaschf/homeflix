"""WatchlistItem aggregate root."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import Field

from src.building_blocks.domain import AggregateRoot
from src.modules.collections.domain.value_objects import ListId


class WatchlistItem(AggregateRoot[ListId]):
    """An item saved to the user's watchlist (My List).

    Represents a movie or series that the user wants to watch later.

    Attributes:
        id: External ID (lst_xxx format).
        media_id: External ID of the media (mov_xxx or ser_xxx).
        media_type: Type of media ("movie" or "series").
        added_at: Timestamp when the item was added.

    Example:
        >>> item = WatchlistItem.create(
        ...     media_id="mov_abc123def456",
        ...     media_type="movie",
        ... )
    """

    id: ListId | None = Field(default=None)

    media_id: str
    media_type: str  # "movie" or "series"
    added_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def create(
        cls,
        media_id: str,
        media_type: str,
    ) -> WatchlistItem:
        """Factory method with automatic ID generation.

        Args:
            media_id: External ID of the media (mov_xxx or ser_xxx).
            media_type: Type of media ("movie" or "series").

        Returns:
            A new WatchlistItem instance.
        """
        return cls(
            id=ListId.generate(),
            media_id=media_id,
            media_type=media_type,
            added_at=datetime.now(UTC),
        )


__all__ = ["WatchlistItem"]
