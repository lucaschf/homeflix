"""Subtitle preference value object."""

from __future__ import annotations

from typing import ClassVar

from pydantic import Field

from src.building_blocks.domain.value_objects import CompoundValueObject


class SubtitlePreference(CompoundValueObject):
    """A recorded subtitle choice: off, or a specific track index.

    Replaces the overloaded ``int | None`` where ``-1`` meant "off" and
    ``None`` meant "no preference". Here the *absence* of a preference is
    modelled by the field being ``None``; a ``SubtitlePreference`` instance
    always represents a concrete choice (off, or a track). The
    wire/persistence format stays an int (``-1`` = off, ``>= 0`` = track
    index) — that mapping is isolated to :meth:`from_wire` / :meth:`to_wire`,
    the single home for the sentinel. Decoding is lenient (any negative
    reads as "off"); encoding canonicalises "off" to ``-1``.

    Attributes:
        track_index: The chosen 0-based track index, or ``None`` for "off".

    Example:
        >>> SubtitlePreference.track(2).is_off
        False
        >>> SubtitlePreference.off().is_off
        True
        >>> SubtitlePreference.to_wire(SubtitlePreference.off())
        -1
        >>> SubtitlePreference.from_wire(2).track_index
        2
    """

    _OFF_WIRE_VALUE: ClassVar[int] = -1

    track_index: int | None = Field(ge=0)

    @classmethod
    def off(cls) -> SubtitlePreference:
        """Subtitles explicitly turned off."""
        return cls(track_index=None)

    @classmethod
    def track(cls, index: int) -> SubtitlePreference:
        """A specific 0-based subtitle track."""
        return cls(track_index=index)

    @property
    def is_off(self) -> bool:
        """Whether subtitles are turned off."""
        return self.track_index is None

    @classmethod
    def from_wire(cls, value: int | None) -> SubtitlePreference | None:
        """Decode the persisted/wire int into a preference.

        Args:
            value: ``None`` (no preference recorded), a negative value
                (off), or a ``>= 0`` track index.

        Returns:
            ``None`` when no preference is recorded, otherwise the
            corresponding :class:`SubtitlePreference`.
        """
        if value is None:
            return None
        return cls.off() if value < 0 else cls.track(value)

    @classmethod
    def to_wire(cls, preference: SubtitlePreference | None) -> int | None:
        """Encode a preference back into the persisted/wire int.

        Args:
            preference: A preference, or ``None`` for "no preference".

        Returns:
            ``None`` when no preference, ``-1`` for off, else the track index.
        """
        if preference is None:
            return None
        return cls._OFF_WIRE_VALUE if preference.is_off else preference.track_index


__all__ = ["SubtitlePreference"]
