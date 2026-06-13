"""WatchlistItem aggregate root."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Self

from pydantic import Field, model_validator

from src.building_blocks.domain import AggregateRoot
from src.modules.collections.domain.value_objects import (
    CollectionMediaId,  # — runtime for Pydantic
    ListId,
)
from src.shared_kernel.value_objects import (
    MediaType,  # — runtime for Pydantic
)
from src.shared_kernel.value_objects.profile_id import ProfileId  # noqa: TCH001


class WatchlistItem(AggregateRoot[ListId]):
    """An item saved to a profile's watchlist (My List).

    Represents a movie or series that the profile wants to watch later.

    Attributes:
        id: External ID (lst_xxx format).
        profile_id: Owning profile (``prf_xxx``).
        media_id: Typed catalog id (``mov_xxx`` or ``ser_xxx``); must
            match ``media_type``.
        media_type: Type of media (movie or series).
        added_at: Timestamp when the item was added.

    Example:
        >>> item = WatchlistItem.create(
        ...     profile_id=caller_profile_id,
        ...     media_id=CollectionMediaId("mov_abc123def456"),
        ...     media_type=MediaType.MOVIE,
        ... )
    """

    id: ListId | None = Field(default=None)

    profile_id: ProfileId
    media_id: CollectionMediaId
    media_type: MediaType
    added_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def _validate_media_id_matches_type(self) -> Self:
        """Reject a movie id paired with series type and vice versa."""
        if self.media_id.is_movie != (self.media_type is MediaType.MOVIE):
            raise ValueError(
                f"media_id '{self.media_id.value}' does not match "
                f"media_type '{self.media_type.value}'",
            )
        return self

    @classmethod
    def create(
        cls,
        profile_id: ProfileId,
        media_id: CollectionMediaId,
        media_type: MediaType,
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
