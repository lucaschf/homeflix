"""DTOs for the intro-detection run (audit) use cases."""

from dataclasses import dataclass, field

from src.modules.media.domain.entities.intro_detection_run import IntroDetectionRun


@dataclass(frozen=True)
class EpisodeDetectionResultOutput:
    """One episode's detection outcome within a run."""

    episode_id: str
    episode_number: int
    start_seconds: float
    end_seconds: float
    confidence: float
    persisted: bool


@dataclass(frozen=True)
class IntroDetectionRunOutput:
    """API projection of an :class:`IntroDetectionRun`."""

    id: str
    series_id: str
    series_title: str
    season_id: str
    season_number: int
    algorithm: str
    outcome: str
    ref_count: int
    analyzed_count: int
    detected_count: int
    persisted_count: int
    min_confidence: float
    error: str | None
    started_at: str
    finished_at: str
    episode_results: list[EpisodeDetectionResultOutput] = field(default_factory=list)


@dataclass(frozen=True)
class ListIntroDetectionRunsInput:
    """Filters + pagination for listing intro-detection runs."""

    season_id: str | None = None
    series_id: str | None = None
    limit: int = 50
    offset: int = 0


@dataclass(frozen=True)
class GetIntroDetectionRunInput:
    """Input for fetching a single run by id."""

    run_id: str


def intro_detection_run_to_output(run: IntroDetectionRun) -> IntroDetectionRunOutput:
    """Project a persisted run aggregate to its API output DTO."""
    if run.id is None:
        raise ValueError("Cannot project an unpersisted IntroDetectionRun to output")
    return IntroDetectionRunOutput(
        id=str(run.id),
        series_id=run.series_id,
        series_title=run.series_title,
        season_id=run.season_id,
        season_number=run.season_number,
        algorithm=run.algorithm,
        outcome=run.outcome.value,
        ref_count=run.ref_count,
        analyzed_count=run.analyzed_count,
        detected_count=run.detected_count,
        persisted_count=run.persisted_count,
        min_confidence=run.min_confidence,
        error=run.error,
        started_at=run.started_at.isoformat(),
        finished_at=run.finished_at.isoformat(),
        episode_results=[
            EpisodeDetectionResultOutput(
                episode_id=r.episode_id,
                episode_number=r.episode_number,
                start_seconds=r.start_seconds,
                end_seconds=r.end_seconds,
                confidence=r.confidence,
                persisted=r.persisted,
            )
            for r in run.episode_results
        ],
    )


__all__ = [
    "EpisodeDetectionResultOutput",
    "GetIntroDetectionRunInput",
    "IntroDetectionRunOutput",
    "ListIntroDetectionRunsInput",
    "intro_detection_run_to_output",
]
