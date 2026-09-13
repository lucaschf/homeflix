"""Watch Progress repository interfaces."""

from src.modules.watch_progress.domain.repositories.watch_progress_repository import (
    RecentlyWatchedCursor,
    RecentlyWatchedPage,
    WatchProgressRepository,
)

__all__ = ["RecentlyWatchedCursor", "RecentlyWatchedPage", "WatchProgressRepository"]
