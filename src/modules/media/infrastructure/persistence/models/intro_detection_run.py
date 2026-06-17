"""IntroDetectionRun ORM model — per-season intro-detection audit row."""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.persistence.base import Base


class IntroDetectionRunModel(Base):
    """SQLAlchemy model for the ``intro_detection_runs`` table.

    Append-only audit log: one row per season processed by the
    detection job. Per-episode detail (confidence + whether persisted)
    lives in the ``episode_results`` JSON column so the wide-but-sparse
    alternative is avoided.

    Attributes:
        series_id: External id of the parent series (ser_xxx).
        season_id: External id of the processed season (ssn_xxx).
        season_number: Season number, denormalized for display.
        algorithm: Detector used (``chromaprint`` | ``frame_hash``).
        outcome: Terminal season state for this run.
        ref_count / analyzed_count / detected_count / persisted_count:
            Per-run counters.
        min_confidence: Confidence floor applied on this run.
        episode_results: Per-episode detection detail (JSON list).
        error: Failure message when ``outcome`` is ``FAILED``.
        started_at / finished_at: Processing window for the season.
    """

    series_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    series_title: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    season_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    season_number: Mapped[int] = mapped_column(Integer, nullable=False)
    algorithm: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    outcome: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    ref_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    analyzed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    detected_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    persisted_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    min_confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    episode_results: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, nullable=False, default=list
    )
    error: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


__all__ = ["IntroDetectionRunModel"]
