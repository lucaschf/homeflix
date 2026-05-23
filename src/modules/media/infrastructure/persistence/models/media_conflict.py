"""MediaConflict ORM model — pending dedup-detection queue row."""

from datetime import datetime

from sqlalchemy import DateTime, Float, String
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.persistence.base import Base


class MediaConflictModel(Base):
    """SQLAlchemy model for the ``media_conflicts`` table.

    Materialises a content-identity collision detected by the
    post-enrich hook (ADR-015). Phase 1 stores only Movie-vs-Movie
    pairs; the schema is already polymorphic via the
    ``candidate_*_type`` discriminator so Series can land later
    without a column add.

    Attributes:
        candidate_a_id: External id of one side (e.g. ``mov_xxx``).
        candidate_a_type: ``"movie"`` (Phase 1) or ``"series"`` (later).
        candidate_b_id: External id of the other side.
        candidate_b_type: Same as ``candidate_a_type``.
        match_reason: ``"tmdb_id"`` or ``"title_year_fallback"``.
        runtime_delta_minutes: Absolute runtime difference, in minutes.
            ``NULL`` when one or both sides lack runtime data.
        suggested_action: Pre-computed hint for the admin UI.
        resolved_at: ``NULL`` while pending; stamped on resolution.
        resolution: Admin-chosen disposition, paired with
            ``resolved_at``.
    """

    candidate_a_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    candidate_a_type: Mapped[str] = mapped_column(String(20), nullable=False)
    candidate_b_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    candidate_b_type: Mapped[str] = mapped_column(String(20), nullable=False)

    match_reason: Mapped[str] = mapped_column(String(30), nullable=False)
    runtime_delta_minutes: Mapped[float | None] = mapped_column(Float, nullable=True)
    suggested_action: Mapped[str] = mapped_column(String(30), nullable=False)

    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
    resolution: Mapped[str | None] = mapped_column(String(30), nullable=True)


__all__ = ["MediaConflictModel"]
