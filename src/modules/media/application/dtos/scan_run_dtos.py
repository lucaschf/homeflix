"""DTOs for scan + enrich run history (admin surface)."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ScanRunOutput:
    """API-facing shape of a scan/enrich run row.

    Always serializable to JSON; counter columns live inside
    ``summary`` so the frontend can render whichever counters
    apply per kind without the response shape changing.
    """

    id: str
    kind: str
    trigger: str
    library_id: str | None
    status: str
    started_at: str
    finished_at: str | None
    summary: dict[str, int]
    errors_count: int
    errors: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class TriggerScanInput:
    """Input for ``TriggerScanUseCase``.

    Carries the library to scan plus a flag the route uses to set
    the ``trigger`` column — the route passes ``manual``, the
    scheduler can call the same path with ``scheduled``.
    """

    library_id: str
    trigger: str = "manual"


@dataclass(frozen=True)
class TriggerBulkEnrichInput:
    """Input for ``TriggerBulkEnrichUseCase``.

    Bulk enrich isn't library-scoped today — the underlying use
    case sweeps every movie + series with missing metadata. The
    ``force`` flag re-enriches even rows that already have
    metadata (used after a TMDB outage when partial data may have
    been written).
    """

    force: bool = False
    trigger: str = "manual"


@dataclass(frozen=True)
class ListScanRunsInput:
    """Input for ``ListScanRunsUseCase``.

    All filters are optional — the unfiltered call returns the
    most recent runs across every kind/trigger/library.
    """

    kind: str | None = None
    trigger: str | None = None
    library_id: str | None = None
    limit: int = 50
    offset: int = 0


@dataclass(frozen=True)
class GetScanRunInput:
    """Input for ``GetScanRunUseCase``."""

    run_id: str


__all__ = [
    "GetScanRunInput",
    "ListScanRunsInput",
    "ScanRunOutput",
    "TriggerBulkEnrichInput",
    "TriggerScanInput",
]
