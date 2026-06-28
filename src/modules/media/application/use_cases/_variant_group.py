"""Parameter object for a group of scanned movie file variants.

Replaces the ``(paths: list[str], by_path: dict[str, ScannedFile])`` pair
that used to travel together through the movie-processing methods: the
list said *which* paths form one logical movie and the dict resolved each
back to its :class:`ScannedFile`. Bundling them removes the repeated
``by_path[path]`` lookups and the long parameter lists.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator

    from src.modules.media.application.ports.file_scanner_port import ScannedFile


@dataclass(frozen=True)
class VariantGroup:
    """The scanned files that are variants of one logical movie.

    The first file is treated as the primary variant; the rest are
    additional quality/format variants of the same movie.

    Attributes:
        files: The scanned files in the group (non-empty; first is primary).
    """

    files: tuple[ScannedFile, ...]

    def __post_init__(self) -> None:
        """Reject an empty group — a group always has at least a primary."""
        if not self.files:
            raise ValueError("VariantGroup requires at least one scanned file")

    @classmethod
    def of(cls, files: Iterable[ScannedFile]) -> VariantGroup:
        """Build a group from scanned files (order preserved)."""
        return cls(tuple(files))

    @property
    def primary(self) -> ScannedFile:
        """The primary variant (first file)."""
        return self.files[0]

    @property
    def additional(self) -> tuple[ScannedFile, ...]:
        """The non-primary variants."""
        return self.files[1:]

    @property
    def paths(self) -> list[str]:
        """The file-path strings of every variant in the group."""
        return [f.file_path.value for f in self.files]

    def __iter__(self) -> Iterator[ScannedFile]:
        """Iterate the scanned files in group order."""
        return iter(self.files)


__all__ = ["VariantGroup"]
