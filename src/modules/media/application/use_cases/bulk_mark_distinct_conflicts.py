"""Bulk mark-distinct resolution for queued conflicts (ADR-015 Phase 4)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.building_blocks.domain.errors import DomainValidationException
from src.modules.media.application.dtos.conflict_dtos import (
    BulkMarkDistinctInput,
    BulkMarkDistinctOutput,
    BulkSkippedConflict,
)
from src.modules.media.domain.entities.media_conflict import ResolutionAction
from src.modules.media.domain.value_objects.media_conflict_id import MediaConflictId

if TYPE_CHECKING:
    from src.modules.media.application.unit_of_work import MediaUnitOfWorkFactory


class BulkMarkDistinctConflictsUseCase:
    """Mark many pending conflicts as intentionally distinct in one pass.

    Bulk resolution is intentionally limited to ``MARK_DISTINCT`` (the
    operator says "these really are different editions"). Unlike the
    MERGE actions it needs no per-conflict winner and triggers no
    soft-delete or cross-BC fan-out, so a whole selection can be
    closed safely in a single transaction.

    Each id is handled independently: ids that don't exist, are
    already resolved, or are malformed are skipped (with a reason)
    rather than aborting the batch. The detector will not re-queue a
    MARK_DISTINCT pair (see ``find_blocking_pair``).

    Args:
        uow_factory: Factory that opens a fresh media Unit of Work.
    """

    def __init__(self, uow_factory: MediaUnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def execute(
        self,
        input_dto: BulkMarkDistinctInput,
    ) -> BulkMarkDistinctOutput:
        """Resolve every pending id as MARK_DISTINCT; skip the rest."""
        unique_ids = _dedupe_preserving_order(input_dto.conflict_ids)

        resolved_ids: list[str] = []
        skipped: list[BulkSkippedConflict] = []

        async with self._uow_factory() as uow:
            for raw_id in unique_ids:
                try:
                    conflict_id = MediaConflictId(raw_id)
                except DomainValidationException:
                    skipped.append(BulkSkippedConflict(raw_id, "invalid_id"))
                    continue

                conflict = await uow.media_conflicts.find_by_id(conflict_id)
                if conflict is None:
                    skipped.append(BulkSkippedConflict(raw_id, "not_found"))
                    continue
                if conflict.is_resolved:
                    skipped.append(BulkSkippedConflict(raw_id, "already_resolved"))
                    continue

                resolved = conflict.resolve(ResolutionAction.MARK_DISTINCT)
                persisted = await uow.media_conflicts.save(resolved)
                resolved_ids.append(str(persisted.id))

        return BulkMarkDistinctOutput(
            requested=len(unique_ids),
            resolved_ids=resolved_ids,
            skipped=skipped,
        )


def _dedupe_preserving_order(ids: list[str]) -> list[str]:
    """Drop duplicate ids while keeping first-seen order."""
    seen: set[str] = set()
    out: list[str] = []
    for raw_id in ids:
        if raw_id in seen:
            continue
        seen.add(raw_id)
        out.append(raw_id)
    return out


__all__ = ["BulkMarkDistinctConflictsUseCase"]
