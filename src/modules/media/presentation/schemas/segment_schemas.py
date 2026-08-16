"""Request schemas for multi-episode file segments (ADR-030)."""

from pydantic import BaseModel, Field


class EpisodeSegmentItem(BaseModel):
    """One episode's window within the shared file.

    Cross-field and cross-segment invariants (``end > start``, no overlap,
    within the file duration) are enforced by the domain / use case; only
    per-field bounds live here.
    """

    episode_number: int = Field(ge=1)
    start_seconds: int = Field(ge=0)
    end_seconds: int = Field(ge=1)


class DefineEpisodeSegmentsRequest(BaseModel):
    """Body for assigning file segments to a season's episodes."""

    season_number: int = Field(ge=0)
    file_path: str = Field(min_length=1)
    segments: list[EpisodeSegmentItem] = Field(min_length=1)


__all__ = ["DefineEpisodeSegmentsRequest", "EpisodeSegmentItem"]
