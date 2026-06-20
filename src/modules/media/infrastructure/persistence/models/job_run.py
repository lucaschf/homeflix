"""JobRun ORM model — generic scheduler-job execution log."""

from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.persistence.base import Base


class JobRunModel(Base):
    """SQLAlchemy model for the ``job_runs`` table.

    One row per execution of any recurring scheduler job. The
    ``job_id`` matches the APScheduler job identifier so the admin
    dashboard can line each live job up with its execution history.

    Attributes:
        job_id: Stable scheduler job id (e.g.
            ``homeflix:thumbnail-backfill``).
        status: ``running`` | ``succeeded`` | ``failed`` |
            ``interrupted`` (the post-restart sweep value).
        started_at: When the tick began.
        finished_at: ``None`` while ``running``; set on terminal states.
        error: Failure message when failed, else ``None``.
    """

    job_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(String(2000), nullable=True)


__all__ = ["JobRunModel"]
