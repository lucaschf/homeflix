"""Episode entity for TV series."""

from __future__ import annotations

from datetime import datetime  # noqa: TCH003 — needed at runtime by Pydantic
from typing import Self

from pydantic import Field, field_validator, model_validator

from src.building_blocks.domain import DomainEntity, utc_now
from src.building_blocks.domain.errors import BusinessRuleViolationException
from src.modules.media.domain.entities.file_variant_mixin import FileVariantMixin
from src.modules.media.domain.rule_codes import MediaRuleCodes
from src.modules.media.domain.value_objects import (
    AirDate,
    CreditsDetectionState,
    CreditsMarker,
    Duration,
    EpisodeId,
    EpisodeNumber,
    ImageUrl,
    IntroMarker,
    IntroStatus,
    LocalizedField,
    LocalizedMetadata,
    MediaFile,
    SeasonNumber,
    SeriesId,
    Title,
)


class Episode(FileVariantMixin, DomainEntity[EpisodeId]):
    """Episode entity belonging to a Season of a Series.

    Represents a single episode of a TV series with its metadata
    and file variants.

    Example:
        >>> episode = Episode(
        ...     series_id=SeriesId.generate(),
        ...     season_number=1,
        ...     episode_number=1,
        ...     title=Title("Pilot"),
        ...     duration=Duration(2700),
        ...     files=[MediaFile(
        ...         file_path=FilePath("/series/show/s01e01.mkv"),
        ...         file_size=1_000_000_000,
        ...         resolution=Resolution("1080p"),
        ...         is_primary=True,
        ...     )],
        ... )
    """

    # Identity
    id: EpisodeId | None = Field(default=None)

    # Relationship
    series_id: SeriesId
    season_number: SeasonNumber
    episode_number: EpisodeNumber

    # Content info
    title: Title
    synopsis: str | None = Field(default=None, max_length=10000)
    duration: Duration

    # Per-language title/synopsis overrides, keyed by BCP-47 tag.
    # ``get_title(lang)`` / ``get_synopsis(lang)`` fall back to the
    # base (English) fields when a locale has no override.
    localized: LocalizedMetadata = Field(default_factory=LocalizedMetadata)

    # File variants
    files: list[MediaFile] = Field(default_factory=list)
    thumbnail_path: ImageUrl | None = None
    scrub_preview_path: ImageUrl | None = None

    # Metadata
    air_date: AirDate | None = None

    # Skip-intro support. ``intro`` holds the span when there is one;
    # ``intro_absent_at`` records that someone confirmed there is none.
    # The timestamp doubles as the flag, so the two fields cover the
    # three states (pending / marked / absent) without a bare boolean —
    # read them through ``intro_status`` rather than pairwise.
    intro: IntroMarker | None = None
    intro_absent_at: datetime | None = None

    # Skip-credits support (per-file detection; credits run to the end)
    credits: CreditsMarker | None = None
    credits_detection_state: CreditsDetectionState = CreditsDetectionState.NOT_STARTED

    # noinspection PyNestedDecorators
    @field_validator("id", mode="before")
    @classmethod
    def convert_id(cls, v: str | EpisodeId | None) -> EpisodeId | None:
        """Convert string to EpisodeId if needed."""
        if v is None:
            return None
        return EpisodeId(v) if isinstance(v, str) else v

    @model_validator(mode="after")
    def _validate_intro_state(self) -> Self:
        """Reject the one combination the three intro states exclude.

        An episode cannot both carry an intro span and be flagged as
        having no intro. The ``with_*`` mutators keep the pair
        consistent; this guards entities built directly (mappers,
        tests) from persisting a contradiction.
        """
        if self.intro is not None and self.intro_absent_at is not None:
            raise ValueError("intro and intro_absent_at cannot both be set")
        return self

    @property
    def intro_status(self) -> IntroStatus:
        """Where this episode stands on having its intro resolved."""
        if self.intro is not None:
            return IntroStatus.MARKED
        if self.intro_absent_at is not None:
            return IntroStatus.ABSENT
        return IntroStatus.PENDING

    @property
    def intro_resolved(self) -> bool:
        """Whether the intro question is settled, marked or absent.

        Coverage counts this rather than "has a marker", so an episode
        that genuinely has no opening sequence stops holding its series
        below full coverage forever.
        """
        return self.intro_status is not IntroStatus.PENDING

    # ── localized accessors ────────────────────────────────────────────

    def get_title(self, lang: str = "en") -> str:
        """Get title in the requested language, falling back to the base."""
        return self.localized.text(LocalizedField.TITLE, lang) or self.title.value

    def get_synopsis(self, lang: str = "en") -> str | None:
        """Get synopsis in the requested language, falling back to the base."""
        return self.localized.text(LocalizedField.SYNOPSIS, lang) or self.synopsis

    def with_intro_marker(self, marker: IntroMarker) -> Self:
        """Return a copy with the intro marker set.

        Args:
            marker: The intro marker to attach to this episode.

        Returns:
            A new Episode with the marker applied, or ``self`` if the
            same marker is already in place.

        Raises:
            BusinessRuleViolationException: If ``marker.end_seconds``
                exceeds the episode's duration.
        """
        if marker.end_seconds > self.duration.value:
            raise BusinessRuleViolationException(
                message="Intro end_seconds cannot exceed episode duration",
                rule_code=MediaRuleCodes.INTRO_EXCEEDS_DURATION,
                tags={
                    "episode_duration": self.duration.value,
                    "intro_end_seconds": marker.end_seconds,
                },
            )
        if self.intro == marker and self.intro_absent_at is None:
            return self
        # Recording a span contradicts "has no intro", so the flag is
        # dropped in the same transition rather than left to a caller.
        return self.with_updates(intro=marker, intro_absent_at=None)

    def with_intro_cleared(self) -> Self:
        """Return a copy with the intro question reopened.

        Drops both the marker and the "no intro" flag, so the episode
        goes back to ``PENDING`` and rejoins the detection queue. This
        is how an operator undoes either decision.

        Returns:
            A new Episode with no intro state, or ``self`` if it was
            already pending.
        """
        if self.intro is None and self.intro_absent_at is None:
            return self
        return self.with_updates(intro=None, intro_absent_at=None)

    def with_intro_marked_absent(self, marked_at: datetime | None = None) -> Self:
        """Return a copy flagged as having no intro at all.

        Records the operator's verdict that this episode has no opening
        sequence to skip. Any existing marker is dropped, since the two
        states are exclusive.

        Args:
            marked_at: When the verdict was recorded. Defaults to now.

        Returns:
            A new Episode in the ``ABSENT`` state, or ``self`` if it was
            already flagged.
        """
        if self.intro is None and self.intro_absent_at is not None:
            return self
        return self.with_updates(intro=None, intro_absent_at=marked_at or utc_now())

    def with_credits_marker(self, marker: CreditsMarker) -> Self:
        """Return a copy with the credits marker set.

        Args:
            marker: The credits marker to attach to this episode.

        Returns:
            A new Episode with the marker applied, or ``self`` if the same
            marker is already in place.

        Raises:
            BusinessRuleViolationException: If ``marker.start_seconds``
                exceeds the episode's duration.
        """
        if marker.start_seconds > self.duration.value:
            raise BusinessRuleViolationException(
                message="Credits start_seconds cannot exceed episode duration",
                rule_code=MediaRuleCodes.CREDITS_EXCEEDS_DURATION,
                tags={
                    "episode_duration": self.duration.value,
                    "credits_start_seconds": marker.start_seconds,
                },
            )
        if self.credits == marker:
            return self
        return self.with_updates(credits=marker)

    def with_credits_cleared(self) -> Self:
        """Return a copy with the credits marker removed.

        Returns:
            A new Episode with ``credits`` set to ``None``, or ``self`` if
            it was already absent.
        """
        if self.credits is None:
            return self
        return self.with_updates(credits=None)

    def with_credits_detection_state(self, state: CreditsDetectionState) -> Self:
        """Return a copy with the credits-detection state set."""
        if self.credits_detection_state == state:
            return self
        return self.with_updates(credits_detection_state=state)


__all__ = ["Episode"]
