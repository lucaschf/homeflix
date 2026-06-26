"""Watchlist DTOs for application layer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.modules.collections.application.ports.media_lookup_port import MediaSummary
    from src.modules.collections.domain.entities import WatchlistItem
    from src.shared_kernel.value_objects import MediaType


@dataclass(frozen=True)
class ToggleWatchlistInput:
    """Input for ToggleWatchlistUseCase."""

    profile_id: str
    media_id: str
    media_type: MediaType


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
    media_type: MediaType
    title: str
    poster_path: str | None
    added_at: str
    year: int | None = None
    runtime_seconds: int | None = None
    genres: tuple[str, ...] = ()
    resolution: str | None = None
    hdr: bool = False
    # Watched fraction in [0, 1], or None when there's no progress.
    progress: float | None = None

    @classmethod
    def from_entity(
        cls,
        entity: WatchlistItem,
        summary: MediaSummary,
        progress: float | None = None,
    ) -> WatchlistItemOutput:
        """Create output DTO from a WatchlistItem entity + media summary."""
        return cls(
            media_id=entity.media_id.value,
            media_type=entity.media_type,
            title=summary.title,
            poster_path=summary.poster_path,
            added_at=entity.added_at.isoformat(),
            year=summary.year,
            runtime_seconds=summary.runtime_seconds,
            genres=summary.genres,
            resolution=summary.resolution,
            hdr=summary.hdr,
            progress=progress,
        )


@dataclass(frozen=True)
class GetWatchlistInput:
    """Input for GetWatchlistUseCase."""

    profile_id: str
    limit: int = 100
    lang: str = "en"
