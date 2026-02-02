"""FilePath value object for media content."""

import re
from pathlib import PurePath, PurePosixPath, PureWindowsPath

from pydantic import model_validator

from src.domain.shared.models import StringValueObject

# Pattern to detect Windows-style paths (e.g., C:\, D:\)
_WINDOWS_PATH_PATTERN = re.compile(r"^[a-zA-Z]:[\\/]")


class FilePath(StringValueObject):
    """Absolute file path for media content.

    Validates that the path is:
    - Absolute (starts with / on Unix or drive letter on Windows)
    - Does not contain directory traversal (..)
    - Non-empty

    Example:
        >>> path = FilePath("/movies/inception.mkv")
        >>> path.filename
        'inception.mkv'
    """

    @model_validator(mode="before")
    @classmethod
    def validate_file_path(cls, value: str) -> str:
        """Validate and normalize the file path.

        Args:
            value: The raw file path string.

        Returns:
            The validated and normalized file path.

        Raises:
            ValueError: If path is invalid, relative, or contains traversal.
        """
        if not isinstance(value, str):
            raise ValueError("FilePath must be a string")

        value = value.strip()

        if not value:
            raise ValueError("FilePath cannot be empty")

        # Check for directory traversal BEFORE normalization
        if ".." in value:
            raise ValueError("FilePath cannot contain directory traversal (..)")

        # Check for absolute path - use appropriate path class
        # PurePath on Linux doesn't recognize Windows paths as absolute
        if _WINDOWS_PATH_PATTERN.match(value):
            path: PurePath = PureWindowsPath(value)
        else:
            path = PurePosixPath(value)

        if not path.is_absolute():
            raise ValueError("FilePath must be an absolute path")

        # Normalize the path (resolve redundant separators)
        normalized = str(path)

        # Check again for traversal after normalization
        if ".." in normalized:
            raise ValueError("FilePath cannot contain directory traversal (..)")

        return normalized

    def _get_path(self) -> PurePath:
        """Get the appropriate PurePath instance for this path."""
        if _WINDOWS_PATH_PATTERN.match(self.value):
            return PureWindowsPath(self.value)
        return PurePosixPath(self.value)

    @property
    def filename(self) -> str:
        """Get the file name from the path.

        Returns:
            The file name without the directory path.
        """
        return self._get_path().name

    @property
    def extension(self) -> str:
        """Get the file extension.

        Returns:
            The file extension including the dot, or empty string if none.
        """
        return self._get_path().suffix

    @property
    def directory(self) -> str:
        """Get the parent directory path.

        Returns:
            The directory containing this file.
        """
        return str(self._get_path().parent)


__all__ = ["FilePath"]
