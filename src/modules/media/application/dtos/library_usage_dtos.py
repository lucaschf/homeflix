"""DTOs for the admin per-library disk-usage panel."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LibraryUsageEntry:
    """Catalog size for one library.

    Attributes:
        library_id: Owning library id.
        size_bytes: Sum of primary-file bytes for the library's movies +
            episodes. This is catalog size (primary variant only), not a
            ``du`` of the library folders — it ranks libraries against
            each other cheaply without touching disk.
    """

    library_id: str
    size_bytes: int


@dataclass(frozen=True)
class LibraryUsageOutput:
    """Per-library usage, sorted largest-first, plus the grand total."""

    libraries: list[LibraryUsageEntry]
    total_bytes: int
