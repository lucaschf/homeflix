"""IntroDetectionRun repository interface."""

from abc import ABC, abstractmethod
from collections.abc import Sequence

from src.modules.media.domain.entities.intro_detection_run import IntroDetectionRun
from src.modules.media.domain.value_objects.intro_detection_run_id import IntroDetectionRunId


class IntroDetectionRunRepository(ABC):
    """Append-only store of per-season intro-detection run records.

    Records are written once by the detection job and read back by the
    admin audit endpoints; there is no update path.
    """

    @abstractmethod
    async def add(self, run: IntroDetectionRun) -> IntroDetectionRun:
        """Insert a new run, assigning an id, and return the saved row.

        Args:
            run: The run to persist (id may be ``None``).

        Returns:
            The persisted run, re-read so server-managed timestamps and
            the assigned id are populated.
        """
        ...

    @abstractmethod
    async def find_by_id(self, run_id: IntroDetectionRunId) -> IntroDetectionRun | None:
        """Look up a non-deleted run by external id."""
        ...

    @abstractmethod
    async def list_paginated(
        self,
        *,
        season_id: str | None = None,
        series_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[IntroDetectionRun]:
        """List runs newest-first, optionally filtered by season/series."""
        ...

    @abstractmethod
    async def count(
        self,
        *,
        season_id: str | None = None,
        series_id: str | None = None,
    ) -> int:
        """Count non-deleted runs matching the filter."""
        ...


__all__ = ["IntroDetectionRunRepository"]
