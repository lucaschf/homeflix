"""DTOs for the subtitle-OCR run (audit) use cases."""

from dataclasses import dataclass, field

from src.modules.media.domain.entities.subtitle_ocr_run import SubtitleOcrRun


@dataclass(frozen=True)
class SubtitleTrackOcrResultOutput:
    """One image subtitle track's OCR outcome within a run."""

    track_index: int
    language: str
    outcome: str
    cue_count: int


@dataclass(frozen=True)
class SubtitleOcrRunOutput:
    """API projection of a :class:`SubtitleOcrRun`."""

    id: str
    media_kind: str
    media_id: str
    media_title: str
    file_path: str
    outcome: str
    image_track_count: int
    extracted_count: int
    error: str | None
    started_at: str
    finished_at: str
    track_results: list[SubtitleTrackOcrResultOutput] = field(default_factory=list)


@dataclass(frozen=True)
class ListSubtitleOcrRunsInput:
    """Filters + pagination for listing subtitle-OCR runs."""

    media_kind: str | None = None
    media_id: str | None = None
    limit: int = 50
    offset: int = 0


@dataclass(frozen=True)
class GetSubtitleOcrRunInput:
    """Input for fetching a single run by id."""

    run_id: str


@dataclass(frozen=True)
class RunSubtitleOcrInput:
    """Input for the manual "OCR this title now" trigger.

    Attributes:
        media_kind: ``movie`` or ``episode``.
        media_id: External id of the movie/episode to OCR.
    """

    media_kind: str
    media_id: str


def subtitle_ocr_run_to_output(run: SubtitleOcrRun) -> SubtitleOcrRunOutput:
    """Project a persisted run aggregate to its API output DTO."""
    if run.id is None:
        raise ValueError("Cannot project an unpersisted SubtitleOcrRun to output")
    return SubtitleOcrRunOutput(
        id=str(run.id),
        media_kind=run.media_kind,
        media_id=run.media_id,
        media_title=run.media_title,
        file_path=run.file_path,
        outcome=run.outcome.value,
        image_track_count=run.image_track_count,
        extracted_count=run.extracted_count,
        error=run.error,
        started_at=run.started_at.isoformat(),
        finished_at=run.finished_at.isoformat(),
        track_results=[
            SubtitleTrackOcrResultOutput(
                track_index=r.track_index,
                language=r.language,
                outcome=r.outcome.value,
                cue_count=r.cue_count,
            )
            for r in run.track_results
        ],
    )


__all__ = [
    "GetSubtitleOcrRunInput",
    "ListSubtitleOcrRunsInput",
    "RunSubtitleOcrInput",
    "SubtitleOcrRunOutput",
    "SubtitleTrackOcrResultOutput",
    "subtitle_ocr_run_to_output",
]
