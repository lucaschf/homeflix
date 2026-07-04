"""SubtitleOcrRun repository interface."""

from abc import ABC, abstractmethod
from collections.abc import Sequence

from src.modules.media.domain.entities.subtitle_ocr_run import SubtitleOcrRun
from src.modules.media.domain.value_objects.subtitle_ocr_run_id import SubtitleOcrRunId


class SubtitleOcrRunRepository(ABC):
    """Append-only store of per-file subtitle-OCR run records.

    Records are written once by the OCR job / manual trigger and read
    back by the admin audit endpoints; there is no update path.
    """

    @abstractmethod
    async def add(self, run: SubtitleOcrRun) -> SubtitleOcrRun:
        """Insert a new run, assigning an id, and return the saved row."""
        ...

    @abstractmethod
    async def find_by_id(self, run_id: SubtitleOcrRunId) -> SubtitleOcrRun | None:
        """Look up a non-deleted run by external id."""
        ...

    @abstractmethod
    async def list_paginated(
        self,
        *,
        media_kind: str | None = None,
        media_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[SubtitleOcrRun]:
        """List runs newest-first, optionally filtered by media kind/id."""
        ...

    @abstractmethod
    async def count(
        self,
        *,
        media_kind: str | None = None,
        media_id: str | None = None,
    ) -> int:
        """Count non-deleted runs matching the filter."""
        ...


__all__ = ["SubtitleOcrRunRepository"]
