"""SubtitleOcrRun aggregate — per-file subtitle-OCR audit row (ADR-027).

One row is appended each time the OCR job (or the manual trigger)
processes a media file that carries image-based subtitles, so operators
can see which titles were processed and, per track, what was extracted
(language + cue count + outcome). Append-only: records are never mutated.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import Field

from src.building_blocks.domain import AggregateRoot, CompoundValueObject
from src.modules.streaming.domain.value_objects.subtitle_ocr_outcome import (
    SubtitleOcrOutcome,  # noqa: TCH001 — runtime field type (pydantic resolves it)
    SubtitleTrackOutcome,  # noqa: TCH001 — runtime field type
)
from src.modules.streaming.domain.value_objects.subtitle_ocr_run_id import SubtitleOcrRunId


class SubtitleTrackOcrResult(CompoundValueObject):
    """One image subtitle track's OCR outcome within a run.

    Attributes:
        track_index: The source subtitle stream index (0-based).
        language: The track language (ISO 639-1).
        outcome: What happened to this track.
        cue_count: Number of subtitle cues OCR'd (``0`` unless the
            outcome is ``EXTRACTED``) — the "how much did we get out"
            signal for the observability page.
    """

    track_index: int
    language: str
    outcome: SubtitleTrackOutcome
    cue_count: int = 0


class SubtitleOcrRun(AggregateRoot[SubtitleOcrRunId]):
    """A single media file's subtitle-OCR run record.

    Attributes:
        id: External id (sor_xxx); assigned by the repository on insert.
        media_kind: ``movie`` or ``episode``.
        media_id: External id of the processed movie/episode.
        media_title: Human label, denormalized at write time so the audit
            row stays self-contained (survives rename/delete).
        file_path: Absolute path to the processed source file.
        outcome: ``COMPLETED`` or ``FAILED``.
        image_track_count: How many image-based subtitle tracks the file
            carried.
        extracted_count: How many tracks produced a text sidecar
            (outcome ``EXTRACTED``).
        track_results: Per-track OCR detail.
        error: Failure message when ``outcome`` is ``FAILED``.
        started_at: When processing the file began.
        finished_at: When the run was recorded.
    """

    id: SubtitleOcrRunId | None = Field(default=None)
    media_kind: str
    media_id: str
    media_title: str = ""
    file_path: str
    outcome: SubtitleOcrOutcome
    image_track_count: int = 0
    extracted_count: int = 0
    track_results: list[SubtitleTrackOcrResult] = Field(default_factory=list)
    error: str | None = None
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


__all__ = ["SubtitleOcrRun", "SubtitleTrackOcrResult"]
