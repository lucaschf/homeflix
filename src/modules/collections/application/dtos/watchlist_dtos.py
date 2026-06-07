"""Watchlist DTOs for application layer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.modules.collections.domain.entities import WatchlistItem
    from src.shared_kernel.value_objects import CollectionMediaType


@dataclass(frozen=True)
class ToggleWatchlistInput:
    """Input for ToggleWatchlistUseCase."""

    profile_id: str
    media_id: str
    media_type: CollectionMediaType


@dataclass(frozen=True)
class ToggleWatchlistOutput:
    """Output for ToggleWatchlistUseCase."""

    media_id: str
    added: bool


@dataclass(frozen=True)
class CheckWatchlistInput:
    """Input for CheckWatchlistUseCase."""

    profile_id: str
    media_id: str


@dataclass(frozen=True)
class WatchlistItemOutput:
    """Output representing a single watchlist item with media metadata."""

    media_id: str
    media_type: CollectionMediaType
    title: str
    poster_path: str | None
    added_at: str

    @classmethod
    def from_entity(
        cls,
        entity: WatchlistItem,
        title: str,
        poster_path: str | None,
    ) -> WatchlistItemOutput:
        """Create output DTO from a WatchlistItem entity with metadata."""
        return cls(
            media_id=entity.media_id.value,
            media_type=entity.media_type,
            title=title,
            poster_path=poster_path,
            added_at=entity.added_at.isoformat(),
        )


@dataclass(frozen=True)
class GetWatchlistInput:
    """Input for GetWatchlistUseCase."""

    profile_id: str
    limit: int = 100
    lang: str = "en"
