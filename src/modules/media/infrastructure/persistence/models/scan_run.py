"""ScanRun ORM model — admin scan/enrich history."""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.persistence.base import Base


class ScanRunModel(Base):
    """SQLAlchemy model for the ``scan_runs`` table.

    Backs both admin-trigger types ("scan a library", "bulk re-enrich
    metadata") and the scheduler's periodic runs. Discrimination
    columns: ``kind`` (``scan`` | ``enrich``) tells *what* ran;
    ``trigger`` (``manual`` | ``scheduled``) tells *who* started it.

    The per-kind counters live inside ``summary`` (JSON), serialized
    from the typed ``ScanCounters`` / ``EnrichCounters`` value objects
    (movies/episodes created+updated for scans; movies/series enriched +
    skipped for enrich). Keeping them in JSON avoids a wide column with
    mostly-null counters for whichever kind didn't run.

    Attributes:
        kind: ``scan`` or ``enrich``.
        trigger: ``manual`` (admin-initiated) or ``scheduled``
            (background poller).
        library_id: External id of the targeted library. ``None``
            for enrich runs that span every library.
        started_at: When the runner began work.
        finished_at: ``None`` while the row is still in
            ``running``; set on the terminal state.
        status: ``running`` | ``succeeded`` | ``failed`` |
            ``interrupted``. ``interrupted`` is the post-restart
            sweep value for rows that were ``running`` when the
            process died.
        summary: Per-kind counter dict serialized as JSON.
        errors: First N error messages emitted during the run.
            Truncated to keep the row size sane.
    """

    kind: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    trigger: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    library_id: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    summary: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    errors: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)


__all__ = ["ScanRunModel"]
