"""DTOs for defining multi-episode file segments (ADR-030)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class EpisodeSegmentSpec:
    """One episode's time window within a shared physical file.

    Attributes:
        episode_number: Episode number within the target season.
        start_seconds: Inclusive start second of the episode in the file.
        end_seconds: Exclusive end second of the episode in the file.
    """

    episode_number: int
    start_seconds: int
    end_seconds: int


@dataclass(frozen=True)
class DefineEpisodeSegmentsInput:
    """Input for ``DefineEpisodeSegmentsUseCase``.

    Attributes:
        series_id: External series ID (``ser_xxx``).
        season_number: Season whose episodes share the file.
        file_path: Absolute path to the shared physical video file.
        segments: One spec per episode carried by the file.
    """

    series_id: str
    season_number: int
    file_path: str
    segments: list[EpisodeSegmentSpec] = field(default_factory=list)


@dataclass(frozen=True)
class AssignedSegmentOutput:
    """A single episode after its segment was assigned.

    Attributes:
        episode_id: External episode ID (``epi_xxx``), or ``None`` if the
            episode is not yet persisted.
        episode_number: Episode number within the season.
        title: Episode display title.
        start_seconds: Assigned segment start.
        end_seconds: Assigned segment end.
        duration_seconds: Playable length (``end - start``), now the
            episode's duration.
    """

    episode_id: str | None
    episode_number: int
    title: str
    start_seconds: int
    end_seconds: int
    duration_seconds: int


@dataclass(frozen=True)
class DefineEpisodeSegmentsOutput:
    """Output for ``DefineEpisodeSegmentsUseCase``.

    Attributes:
        series_id: External series ID the segments were applied to.
        season_number: Target season number.
        file_path: The shared physical file the episodes now reference.
        episodes: The episodes updated, in ascending start order.
    """

    series_id: str
    season_number: int
    file_path: str
    episodes: list[AssignedSegmentOutput]


__all__ = [
    "AssignedSegmentOutput",
    "DefineEpisodeSegmentsInput",
    "DefineEpisodeSegmentsOutput",
    "EpisodeSegmentSpec",
]
