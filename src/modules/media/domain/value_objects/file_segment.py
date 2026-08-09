"""FileSegment value object — a time window within a shared physical file."""

from typing import Self

from pydantic import Field, model_validator

from src.building_blocks.domain import CompoundValueObject


class FileSegment(CompoundValueObject):
    """A ``[start, end)`` time window a title occupies within a physical file.

    Present when a single video file contains several titles (e.g. an old
    mini-series with two episodes concatenated in one ``.mkv``). When a
    :class:`MediaFile` carries no segment (``None``) it represents the whole
    file, which is the default and the pre-existing behaviour.

    Offsets are in source seconds, measured from the start of the physical
    file (not the title). ``end_seconds`` is exclusive, so the playable
    length of the segment is ``end_seconds - start_seconds``.

    Attributes:
        start_seconds: Second (inclusive) where the title begins in the
            file. Must be ``>= 0``.
        end_seconds: Second (exclusive) where the title ends in the file.
            Must be strictly greater than ``start_seconds``.

    Example:
        >>> # Second episode occupying 01:19:00 to 02:38:00 of a shared file
        >>> FileSegment(start_seconds=4740, end_seconds=9480).duration_seconds
        4740
    """

    start_seconds: int = Field(ge=0)
    end_seconds: int = Field(ge=1)

    @model_validator(mode="after")
    def _validate_range(self) -> Self:
        """Enforce that the window is non-empty and correctly ordered."""
        if self.end_seconds <= self.start_seconds:
            raise ValueError("end_seconds must be greater than start_seconds")
        return self

    @property
    def duration_seconds(self) -> int:
        """Return the playable length of the segment in seconds."""
        return self.end_seconds - self.start_seconds


__all__ = ["FileSegment"]
