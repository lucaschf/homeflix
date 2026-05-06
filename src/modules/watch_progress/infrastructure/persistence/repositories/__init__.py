"""Watch Progress repository implementations."""

from src.modules.watch_progress.infrastructure.persistence.repositories.watch_progress_repository import (
    SQLAlchemyWatchProgressRepository,
)

__all__ = ["SQLAlchemyWatchProgressRepository"]
