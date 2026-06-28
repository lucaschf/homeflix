"""MediaConflict repository interface."""

from abc import ABC, abstractmethod

from src.building_blocks.domain.pagination import PaginatedResult
from src.modules.media.domain.entities.media_conflict import (
    MediaConflict,
    ResolutionSource,
)
from src.modules.media.domain.value_objects.media_conflict_id import MediaConflictId


class MediaConflictRepository(ABC):
    """Repository interface for the ``MediaConflict`` aggregate.

    Port for the ADR-015 conflict queue. Phase 1 only exposes the
    read + create surface needed by the detection hook and the
    admin list endpoint. Resolution writes land in a later phase.
    """

    @abstractmethod
    async def save(self, conflict: MediaConflict) -> MediaConflict:
        """Persist a conflict (create or update).

        Args:
            conflict: The conflict to save.

        Returns:
            The saved conflict (with assigned id if new).
        """
        ...

    @abstractmethod
    async def find_by_id(self, conflict_id: MediaConflictId) -> MediaConflict | None:
        """Look up a conflict by its external id.

        Returns:
            The conflict if found, ``None`` otherwise.
        """
        ...

    @abstractmethod
    async def find_blocking_pair(
        self,
        candidate_a_id: str,
        candidate_b_id: str,
    ) -> MediaConflict | None:
        """Return any row that should suppress re-queueing for the pair.

        Used by the detector to skip pairs already queued *or* already
        resolved as ``MARK_DISTINCT`` — the operator's "these are
        intentionally distinct" verdict must persist across future
        enrichment passes. Comparison is unordered: ``(A, B)`` and
        ``(B, A)`` match the same row.

        Returns:
            The blocking conflict (most recent if multiple), or
            ``None`` when neither a pending nor a MARK_DISTINCT row
            exists. MERGE-resolved rows do not block — by the time
            they are queried the loser is soft-deleted and the
            detector cannot rediscover the pair anyway.
        """
        ...

    @abstractmethod
    async def list_pending(
        self,
        *,
        cursor: str | None = None,
        limit: int = 20,
    ) -> PaginatedResult[MediaConflict]:
        """List unresolved conflicts, newest first.

        Args:
            cursor: Opaque pagination cursor from the previous page.
            limit: Page size.

        Returns:
            Paginated page of pending conflicts.
        """
        ...

    @abstractmethod
    async def list_resolved(
        self,
        *,
        source: ResolutionSource | None = None,
        cursor: str | None = None,
        limit: int = 20,
    ) -> PaginatedResult[MediaConflict]:
        """List resolved conflicts (audit view), newest first.

        Args:
            source: Optional ``ResolutionSource`` filter. ``None``
                returns every resolved row; ``AUTO`` returns only
                rows the detector silently merged; ``MANUAL`` returns
                only rows the admin resolved through the endpoint.
            cursor: Opaque pagination cursor from the previous page.
            limit: Page size.

        Returns:
            Paginated page of resolved conflicts.
        """
        ...


__all__ = ["MediaConflictRepository"]
