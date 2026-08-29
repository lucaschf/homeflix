"""Streaming bounded-context Unit of Work interface.

Covers the streaming-owned aggregates that participate in a single
transaction. Today that is the append-only ``SubtitleOcrRun`` audit log
(ADR-027); the concrete implementation lives in the infrastructure layer
and shares the app-wide SQLAlchemy session factory.
"""

from abc import ABC, abstractmethod

from src.building_blocks.application.unit_of_work import UnitOfWork
from src.modules.streaming.domain.repositories import SubtitleOcrRunRepository


class StreamingUnitOfWork(UnitOfWork):
    """Transactional boundary for streaming-side aggregate operations.

    Subclasses populate ``subtitle_ocr_runs`` on ``__aenter__`` so writes
    within the same ``async with`` block share a transaction.
    """

    subtitle_ocr_runs: SubtitleOcrRunRepository


class StreamingUnitOfWorkFactory(ABC):
    """Builds fresh ``StreamingUnitOfWork`` instances on demand."""

    @abstractmethod
    def __call__(self) -> StreamingUnitOfWork:
        """Return a brand-new, not-yet-entered UoW."""


__all__ = ["StreamingUnitOfWork", "StreamingUnitOfWorkFactory"]
