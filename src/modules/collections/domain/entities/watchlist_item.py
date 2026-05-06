"""WatchlistItem aggregate root."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import Field

from src.building_blocks.domain import AggregateRoot
from src.modules.collections.domain.value_objects import ListId
from src.shared_kernel.value_objects import (
    CollectionMediaType,  # noqa: TCH001 — runtime for Pydantic
)
from src.shared_kernel.value_objects.profile_id import ProfileId  # noqa: TCH001


class WatchlistItem(AggregateRoot[ListId]):
    """An item saved to a profile's watchlist (My List).

    Represents a movie or series that the profile wants to watch later.

    Attributes:
        id: External ID (lst_xxx format).
        profile_id: Owning profile (``prf_xxx``).
        media_id: External ID of the media (mov_xxx or ser_xxx).
        media_type: Type of media (movie or series).
        added_at: Timestamp when the item was added.

    Example:
        >>> item = WatchlistItem.create(
        ...     profile_id=caller_profile_id,
        ...     media_id="mov_abc123def456",
        ...     media_type=CollectionMediaType.MOVIE,
        ... )
    """

    id: ListId | None = Field(default=None)

    profile_id: ProfileId
    media_id: str
    media_type: CollectionMediaType
    added_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def create(
        cls,
        profile_id: ProfileId,
        media_id: str,
        media_type: CollectionMediaType,
    ) -> WatchlistItem:
        """Factory method with automatic ID generation."""
        return cls(
            id=ListId.generate(),
            profile_id=profile_id,
            media_id=media_id,
            media_type=media_type,
            added_at=datetime.now(UTC),
        )


__all__ = ["WatchlistItem"]
