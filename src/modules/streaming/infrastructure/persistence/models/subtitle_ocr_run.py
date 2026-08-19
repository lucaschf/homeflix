"""SubtitleOcrRun ORM model — per-file subtitle-OCR audit row."""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.persistence.base import Base


class SubtitleOcrRunModel(Base):
    """SQLAlchemy model for the ``subtitle_ocr_runs`` table.

    Append-only audit log: one row per media file with image-based
    subtitles processed by the OCR job / manual trigger. Per-track detail
    (language, outcome, cue count) lives in the ``track_results`` JSON
    column so the wide-but-sparse alternative is avoided.

    Attributes:
        media_kind: ``movie`` or ``episode``.
        media_id: External id of the processed movie/episode.
        media_title: Human label, denormalized for display.
        file_path: Absolute path to the processed source file.
        outcome: ``completed`` | ``failed``.
        image_track_count: Image subtitle tracks the file carried.
        extracted_count: Tracks that produced a text sidecar.
        track_results: Per-track OCR detail (JSON list).
        error: Failure message when ``outcome`` is ``failed``.
        started_at / finished_at: Processing window for the file.
    """

    media_kind: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    media_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    media_title: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    file_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    outcome: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    image_track_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    extracted_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    track_results: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    error: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


__all__ = ["SubtitleOcrRunModel"]
