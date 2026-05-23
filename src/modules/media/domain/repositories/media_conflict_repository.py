"""MediaConflict repository interface."""

from abc import ABC, abstractmethod

from src.building_blocks.application.pagination import PaginatedResult
from src.modules.media.domain.entities.media_conflict import MediaConflict
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
    async def find_pending_by_pair(
        self,
        candidate_a_id: str,
        candidate_b_id: str,
    ) -> MediaConflict | None:
        """Find an unresolved conflict for the given candidate pair.

        The detector calls this before persisting a new row so the
        same pair doesn't re-queue on every enrichment pass. The
        comparison is unordered: ``(A, B)`` and ``(B, A)`` match
        the same row.

        Args:
            candidate_a_id: One side of the pair.
            candidate_b_id: The other side of the pair.

        Returns:
            The pending conflict if one exists, ``None`` otherwise.
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


__all__ = ["MediaConflictRepository"]
