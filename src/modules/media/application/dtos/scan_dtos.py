"""DTOs for media scanning operations."""

from dataclasses import dataclass, field

from src.shared_kernel.value_objects.file_path import FilePath


@dataclass(frozen=True)
class ScanMediaInput:
    """Input for media directory scanning.

    Attributes:
        directories: Directories to scan. If empty, uses settings defaults.
    """

    directories: list[FilePath] = field(default_factory=list)


@dataclass(frozen=True)
class ScanMediaOutput:
    """Output of a media directory scan.

    Attributes:
        movies_created: Number of new movies registered.
        movies_updated: Number of existing movies updated with new variants.
        episodes_created: Number of new episodes registered.
        episodes_updated: Number of existing episodes updated.
        errors: List of error messages for files that could not be processed.
    """

    movies_created: int
    movies_updated: int
    episodes_created: int
    episodes_updated: int
    errors: list[str] = field(default_factory=list)


__all__ = ["ScanMediaInput", "ScanMediaOutput"]
