"""PlaybackPosition value object — the playhead within a media's duration."""

from pydantic import Field

from src.building_blocks.domain import CompoundValueObject


class PlaybackPosition(CompoundValueObject):
    """Where playback sits within the media, as ``(position, duration)``.

    Bundles the current playhead and the total duration into one value so
    the progress arithmetic (watched ratio, percentage, completion check)
    lives on the data instead of in stateless helpers. Both components are
    seconds measured from the start of the media.

    ``position_seconds`` may legitimately exceed ``duration_seconds`` for a
    beat: the player can report a position against a stale duration before
    the corrected duration arrives (see ``WatchProgress.update_position``),
    so the ratio is clamped by the caller rather than rejected here. The
    only hard invariants are non-negative position and positive duration.

    Attributes:
        position_seconds: Current playhead in seconds. Must be ``>= 0``.
        duration_seconds: Total media duration in seconds. Must be ``>= 1``.

    Example:
        >>> PlaybackPosition(position_seconds=3600, duration_seconds=7200).percentage
        50.0
    """

    position_seconds: int = Field(ge=0)
    duration_seconds: int = Field(ge=1)

    @property
    def ratio(self) -> float:
        """Fraction of the media watched (``0.0``+), unclamped."""
        return self.position_seconds / self.duration_seconds

    @property
    def percentage(self) -> float:
        """Watched percentage, clamped to ``0-100``."""
        return min(100.0, self.ratio * 100)

    def reaches_completion(self, threshold: float) -> bool:
        """Whether the watched ratio crosses ``threshold`` (e.g. ``0.9``)."""
        return self.ratio >= threshold


__all__ = ["PlaybackPosition"]
