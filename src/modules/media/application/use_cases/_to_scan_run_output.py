"""Internal helper projecting a ``ScanRun`` aggregate into the API DTO."""

from src.modules.media.application.dtos.scan_run_dtos import ScanRunOutput
from src.modules.media.domain.entities.scan_run import ScanRun


def scan_run_to_output(run: ScanRun) -> ScanRunOutput:
    """Convert a ``ScanRun`` to ``ScanRunOutput`` (timestamps as ISO-8601)."""
    if run.id is None:
        raise ValueError("Cannot project an unpersisted ScanRun to output")
    return ScanRunOutput(
        id=str(run.id),
        kind=run.kind.value,
        trigger=run.trigger.value,
        library_id=run.library_id,
        status=run.status.value,
        started_at=run.started_at.isoformat(),
        finished_at=run.finished_at.isoformat() if run.finished_at else None,
        summary={k: int(v) for k, v in run.summary.items()},
        errors_count=len(run.errors),
        errors=list(run.errors),
    )


__all__ = ["scan_run_to_output"]
