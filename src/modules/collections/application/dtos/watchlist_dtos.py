"""Watchlist DTOs for application layer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.modules.collections.domain.entities import WatchlistItem


@dataclass(frozen=True)
class ToggleWatchlistInput:
    """Input for ToggleWatchlistUseCase.

    Attributes:
        media_id: External ID of the media (mov_xxx or ser_xxx).
        media_type: Type of media ("movie" or "series").
    """

    media_id: str
    media_type: str


@dataclass(frozen=True)
class ToggleWatchlistOutput:
    """Output for ToggleWatchlistUseCase.

    Attributes:
        media_id: External ID of the media.
        added: True if added to list, False if removed.
    """

    media_id: str
    added: bool


@dataclass(frozen=True)
class WatchlistItemOutput:
    """Output representing a single watchlist item with media metadata.

    Attributes:
        media_id: External ID of the media.
        media_type: Type of media.
        title: Display title (localized).
        poster_path: URL to poster image.
        added_at: ISO timestamp when added to watchlist.
    """

    media_id: str
    media_type: str
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
        """Create output DTO from a WatchlistItem entity with metadata.

        Args:
            entity: The WatchlistItem domain entity.
            title: Localized display title.
            poster_path: URL to poster image.

        Returns:
            WatchlistItemOutput DTO.
        """
        return cls(
            media_id=entity.media_id,
            media_type=entity.media_type,
            title=title,
            poster_path=poster_path,
            added_at=entity.added_at.isoformat(),
        )


@dataclass(frozen=True)
class GetWatchlistInput:
    """Input for GetWatchlistUseCase.

    Attributes:
        limit: Maximum number of items to return.
        lang: Language code for localized metadata.
    """

    limit: int = 100
    lang: str = "en"
