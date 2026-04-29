"""Season entity for TV series."""

from __future__ import annotations

from datetime import datetime  # noqa: TCH003 — needed at runtime by Pydantic
from typing import TYPE_CHECKING, Self

from pydantic import Field, field_validator

from src.building_blocks.domain import DomainEntity, utc_now
from src.building_blocks.domain.errors import BusinessRuleViolationException
from src.modules.media.domain.rule_codes import MediaRuleCodes
from src.modules.media.domain.value_objects import (
    AirDate,
    EpisodeNumber,
    ImageUrl,
    IntroDetectionState,
    SeasonId,
    SeasonNumber,
    SeriesId,
    Title,
)

if TYPE_CHECKING:
    from src.modules.media.domain.entities.episode import Episode


class Season(DomainEntity[SeasonId]):
    """Season entity belonging to a Series, containing Episodes.

    Represents a season of a TV series with its metadata
    and episode collection.

    Example:
        >>> season = Season(
        ...     series_id=SeriesId.generate(),
        ...     season_number=1,
        ...     title=Title("Season One"),
        ... )
    """

    # Identity - override base id type
    id: SeasonId | None = Field(default=None)

    # Relationship
    series_id: SeriesId
    season_number: SeasonNumber

    # Content info
    title: Title | None = None
    synopsis: str | None = Field(default=None, max_length=10000)
    poster_path: ImageUrl | None = None

    # Metadata
    air_date: AirDate | None = None

    # Composition
    episodes: list[Episode] = Field(default_factory=list)

    # Intro detection (auto-detection job state — manual markers on
    # individual episodes are independent of this state)
    intro_detection_state: IntroDetectionState = IntroDetectionState.NOT_STARTED
    intro_detection_attempted_at: datetime | None = None
    intro_detection_error: str | None = Field(default=None, max_length=2000)

    # noinspection PyNestedDecorators
    @field_validator("id", mode="before")
    @classmethod
    def convert_id(cls, v: str | SeasonId | None) -> SeasonId | None:
        """Convert string to SeasonId if needed."""
        if v is None:
            return None
        return SeasonId(v) if isinstance(v, str) else v

    @property
    def episode_count(self) -> int:
        """Return the number of episodes in this season.

        Returns:
            The count of episodes.
        """
        return len(self.episodes)

    def with_episode(self, episode: Episode) -> Self:
        """Return a copy with the episode added.

        Args:
            episode: The episode to add.

        Returns:
            A new Season with the episode added, or self if already present.

        Raises:
            BusinessRuleViolationException: If episode series_id or season_number doesn't match.
        """
        if episode.series_id != self.series_id:
            raise BusinessRuleViolationException(
                message="Episode series_id must match Season series_id",
                rule_code=MediaRuleCodes.EPISODE_SERIES_MISMATCH,
            )
        if episode.season_number != self.season_number:
            raise BusinessRuleViolationException(
                message="Episode season_number must match Season",
                rule_code=MediaRuleCodes.EPISODE_SEASON_MISMATCH,
            )
        if episode in self.episodes:
            return self
        return self.with_updates(episodes=[*self.episodes, episode])

    def get_episode(self, episode_number: EpisodeNumber | int) -> Episode | None:
        """Find an episode by its number.

        Args:
            episode_number: The episode number to find.

        Returns:
            The Episode if found, None otherwise.
        """
        needle = (
            episode_number
            if isinstance(episode_number, EpisodeNumber)
            else EpisodeNumber(episode_number)
        )
        return next(
            (ep for ep in self.episodes if ep.episode_number == needle),
            None,
        )

    # ── intro detection state transitions ─────────────────────────────

    def with_detection_started(self) -> Self:
        """Mark detection as IN_PROGRESS.

        Returns:
            A new Season in IN_PROGRESS state with the previous error
            cleared.

        Raises:
            BusinessRuleViolationException: If detection is already in
                progress, or DISABLED (must be reset first).
        """
        self._guard_transition(IntroDetectionState.IN_PROGRESS)
        return self.with_updates(
            intro_detection_state=IntroDetectionState.IN_PROGRESS,
            intro_detection_error=None,
        )

    def with_detection_completed(self, attempted_at: datetime | None = None) -> Self:
        """Mark detection as COMPLETED.

        Args:
            attempted_at: When the detection ran. Defaults to ``utc_now()``.

        Returns:
            A new Season in COMPLETED state with the error cleared.
        """
        return self.with_updates(
            intro_detection_state=IntroDetectionState.COMPLETED,
            intro_detection_attempted_at=attempted_at or utc_now(),
            intro_detection_error=None,
        )

    def with_detection_failed(self, error: str, attempted_at: datetime | None = None) -> Self:
        """Mark detection as FAILED with a diagnostic message.

        Args:
            error: Short diagnostic message (truncated to 2000 chars by
                the field constraint).
            attempted_at: When the detection ran. Defaults to ``utc_now()``.

        Returns:
            A new Season in FAILED state with the error captured.
        """
        return self.with_updates(
            intro_detection_state=IntroDetectionState.FAILED,
            intro_detection_attempted_at=attempted_at or utc_now(),
            intro_detection_error=error,
        )

    def with_detection_marked_insufficient(self, attempted_at: datetime | None = None) -> Self:
        """Mark detection as INSUFFICIENT_EPISODES.

        The job uses this when the season does not have enough episodes
        for the cross-correlation algorithm to converge. The state will
        be retried automatically once more episodes are added (the job
        looks for INSUFFICIENT_EPISODES seasons whose episode count has
        grown).

        Args:
            attempted_at: When the detection ran. Defaults to ``utc_now()``.

        Returns:
            A new Season in INSUFFICIENT_EPISODES state.
        """
        return self.with_updates(
            intro_detection_state=IntroDetectionState.INSUFFICIENT_EPISODES,
            intro_detection_attempted_at=attempted_at or utc_now(),
            intro_detection_error=None,
        )

    def with_detection_disabled(self) -> Self:
        """Mark detection as DISABLED.

        Use when fpcalc is unavailable on the host or the season is
        explicitly opted out by configuration. Manual markers on
        individual episodes still work.

        Returns:
            A new Season in DISABLED state.
        """
        return self.with_updates(
            intro_detection_state=IntroDetectionState.DISABLED,
            intro_detection_error=None,
        )

    def with_detection_reset(self) -> Self:
        """Reset detection state to NOT_STARTED.

        Clears the error and the attempted_at timestamp. Used when the
        operator wants the next job tick to re-process the season from
        scratch (e.g. after fpcalc was installed).

        Returns:
            A new Season in NOT_STARTED state.
        """
        return self.with_updates(
            intro_detection_state=IntroDetectionState.NOT_STARTED,
            intro_detection_attempted_at=None,
            intro_detection_error=None,
        )

    def _guard_transition(self, target: IntroDetectionState) -> None:
        """Block invalid intro-detection state transitions.

        Args:
            target: The state we want to transition to.

        Raises:
            BusinessRuleViolationException: If the transition is not allowed.
        """
        current = self.intro_detection_state

        if target == IntroDetectionState.IN_PROGRESS:
            if current == IntroDetectionState.IN_PROGRESS:
                raise BusinessRuleViolationException(
                    message="Intro detection is already in progress for this season",
                    rule_code=MediaRuleCodes.INTRO_DETECTION_INVALID_TRANSITION,
                    tags={"current_state": current.value, "target_state": target.value},
                )
            if current == IntroDetectionState.DISABLED:
                raise BusinessRuleViolationException(
                    message=(
                        "Intro detection is disabled for this season — reset before "
                        "starting a new run"
                    ),
                    rule_code=MediaRuleCodes.INTRO_DETECTION_INVALID_TRANSITION,
                    tags={"current_state": current.value, "target_state": target.value},
                )


__all__ = ["Season"]
