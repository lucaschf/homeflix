"""Translate between :class:`ScanRun` aggregates and the ORM row."""

from src.modules.media.domain.entities.scan_run import (
    ScanRun,
    ScanRunKind,
    ScanRunStatus,
    ScanRunTrigger,
)
from src.modules.media.domain.value_objects.scan_run_id import ScanRunId
from src.modules.media.infrastructure.persistence.models.scan_run import ScanRunModel


class ScanRunMapper:
    """Pure functions converting entity ↔ ``ScanRunModel``."""

    @staticmethod
    def to_entity(model: ScanRunModel) -> ScanRun:
        """Hydrate the aggregate from a row, including timestamps."""
        return ScanRun(
            id=ScanRunId(model.external_id),
            kind=ScanRunKind(model.kind),
            trigger=ScanRunTrigger(model.trigger),
            library_id=model.library_id,
            started_at=model.started_at,
            finished_at=model.finished_at,
            status=ScanRunStatus(model.status),
            summary=dict(model.summary or {}),
            errors=list(model.errors or []),
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    @staticmethod
    def to_model(entity: ScanRun) -> ScanRunModel:
        """Build a fresh ``ScanRunModel`` from a brand-new aggregate."""
        if entity.id is None:
            raise ValueError("ScanRun must have an id before mapping to model")
        return ScanRunModel(
            external_id=str(entity.id),
            kind=entity.kind.value,
            trigger=entity.trigger.value,
            library_id=entity.library_id,
            started_at=entity.started_at,
            finished_at=entity.finished_at,
            status=entity.status.value,
            summary=dict(entity.summary),
            errors=list(entity.errors),
        )

    @staticmethod
    def update_model(model: ScanRunModel, entity: ScanRun) -> None:
        """Copy mutable fields from the entity onto an existing row."""
        model.kind = entity.kind.value
        model.trigger = entity.trigger.value
        model.library_id = entity.library_id
        model.started_at = entity.started_at
        model.finished_at = entity.finished_at
        model.status = entity.status.value
        model.summary = dict(entity.summary)
        model.errors = list(entity.errors)


__all__ = ["ScanRunMapper"]
