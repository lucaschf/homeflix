"""DTOs for the media-conflict use cases (ADR-015 Phase 1)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime


@dataclass(frozen=True)
class DetectMovieConflictsInput:
    """Input for the post-enrich conflict detector.

    Attributes:
        media_id: External id of the just-enriched movie (``mov_xxx``).
        tmdb_id: TMDB numeric id the enrichment locked onto.
    """

    media_id: str
    tmdb_id: int


@dataclass(frozen=True)
class DetectMovieConflictsOutput:
    """Result summary for one detector invocation.

    Attributes:
        conflicts_created: How many ``MediaConflict`` rows were
            persisted as a result of this run. Zero is the typical
            case (no collision, or collision already queued).
        conflict_ids: External ids of the newly-created conflict rows.
    """

    conflicts_created: int
    conflict_ids: list[str]


@dataclass(frozen=True)
class ListConflictsInput:
    """Input for the admin conflict-list endpoint.

    Attributes:
        state: ``"pending"`` (default — the operator queue) or
            ``"resolved"`` (audit view).
        source: Optional resolution-source filter, only meaningful
            when ``state == "resolved"``. ``"manual"`` shows admin
            decisions, ``"auto"`` shows the post-enrich auto-merges
            (ADR-015 Phase 3), ``None`` shows both.
        cursor: Opaque pagination cursor from the previous page.
        limit: Page size; the route already clamps to a sensible
            ``[1, MAX_PAGE_SIZE]`` range.
    """

    state: str = "pending"
    source: str | None = None
    cursor: str | None = None
    limit: int = 20


@dataclass(frozen=True)
class ConflictCandidateFile:
    """Display-side projection of one file variant of a candidate.

    Gives the operator the on-disk context needed to tell two
    catalog entries apart (which is the 720p rip, which path moved,
    etc.) without leaving the conflict queue.

    Attributes:
        file_path: Absolute path of the variant on disk.
        resolution: Resolution label (e.g. ``"1080p"``).
        file_size: Size in bytes; the UI formats it for display.
        video_codec: Codec label (``"h265"``…) or ``None`` when
            unprobed.
        hdr_format: HDR label (``"dolby_vision"``…) or ``None``.
        is_primary: Whether this is the preferred variant.
    """

    file_path: str
    resolution: str
    file_size: int
    video_codec: str | None
    hdr_format: str | None
    is_primary: bool


@dataclass(frozen=True)
class ConflictCandidateSummary:
    """Display-side projection of one side of a conflict pair.

    Attributes:
        media_id: External id (``mov_xxx``).
        media_type: ``"movie"`` (Phase 1) or ``"series"`` (later).
        title: Human-readable title for the admin list. ``None`` when
            the underlying entity has disappeared (soft-deleted or
            hard-deleted out of band).
        year: Release year, when available.
        files: File variants of the candidate, so the operator can
            compare paths / resolutions side by side. Empty when the
            entity has vanished or carries no variants.
    """

    media_id: str
    media_type: str
    title: str | None
    year: int | None
    files: list[ConflictCandidateFile]


@dataclass(frozen=True)
class ConflictSummary:
    """One row in the admin conflict queue or audit view.

    Attributes:
        conflict_id: External id of the conflict (``cnf_xxx``).
        candidate_a: Display projection of one side.
        candidate_b: Display projection of the other side.
        match_reason: Which identity rule fired.
        runtime_delta_minutes: Absolute runtime difference in
            minutes, or ``None`` when unavailable.
        suggested_action: Pre-computed hint for the admin UI.
        detected_at: When the conflict landed in the queue.
        resolved_at: ``None`` while pending; ISO timestamp once the
            row leaves the queue (manual resolve or auto-merge).
        resolution: Resolution action that closed the row; ``None``
            while pending.
        winner_id: Surviving candidate for MERGE resolutions; ``None``
            for pending or MARK_DISTINCT rows.
        resolution_source: ``"manual"`` (admin endpoint) or
            ``"auto"`` (Phase 3 detector); ``None`` while pending.
    """

    conflict_id: str
    candidate_a: ConflictCandidateSummary
    candidate_b: ConflictCandidateSummary
    match_reason: str
    runtime_delta_minutes: float | None
    suggested_action: str
    detected_at: datetime
    resolved_at: datetime | None = None
    resolution: str | None = None
    winner_id: str | None = None
    resolution_source: str | None = None


@dataclass(frozen=True)
class ResolveMediaConflictInput:
    """Input for the admin resolution endpoint.

    Attributes:
        conflict_id: External id of the conflict to resolve.
        action: Which disposition the operator picked.
        winner_id: Required for ``MERGE_KEEP_BOTH`` / ``MERGE_REPLACE``;
            forbidden for ``MARK_DISTINCT``. Must equal one of the
            conflict's candidate ids.
    """

    conflict_id: str
    action: str
    winner_id: str | None = None


@dataclass(frozen=True)
class ResolveMediaConflictOutput:
    """Result summary after the resolve use case commits.

    Attributes:
        conflict_id: External id of the resolved conflict.
        action: The persisted resolution value.
        winner_id: Surviving candidate for MERGE actions; ``None``
            for MARK_DISTINCT.
        loser_id: Soft-deleted candidate for MERGE actions; ``None``
            for MARK_DISTINCT.
        variants_transferred: For ``MERGE_KEEP_BOTH``, how many
            file variants moved from loser → winner. ``0`` for the
            other actions.
    """

    conflict_id: str
    action: str
    winner_id: str | None
    loser_id: str | None
    variants_transferred: int


@dataclass(frozen=True)
class ListConflictsOutput:
    """Paginated list of conflicts.

    Attributes:
        items: The page's conflict summaries, newest-first.
        next_cursor: Opaque token to fetch the next page; ``None``
            when the queue has been exhausted.
        has_more: Convenience flag mirroring ``next_cursor is not
            None``.
    """

    items: list[ConflictSummary]
    next_cursor: str | None
    has_more: bool


__all__ = [
    "ConflictCandidateFile",
    "ConflictCandidateSummary",
    "ConflictSummary",
    "DetectMovieConflictsInput",
    "DetectMovieConflictsOutput",
    "ListConflictsInput",
    "ListConflictsOutput",
    "ResolveMediaConflictInput",
    "ResolveMediaConflictOutput",
]
