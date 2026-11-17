"""FilePath value object for filesystem paths."""

import re
from pathlib import PurePath, PurePosixPath, PureWindowsPath

from pydantic import model_validator

from src.building_blocks.domain.value_objects import StringValueObject

# Pattern to detect Windows-style paths (e.g., C:\, D:\) and UNC paths (e.g., \\server\share)
_WINDOWS_PATH_PATTERN = re.compile(r"^(?:[a-zA-Z]:[\\/]|\\\\[^\\]+\\[^\\]+)")


def _is_parent_reference(part: str) -> bool:
    """Whether a path component is ``..``, or one Windows can trim to it.

    Windows drops trailing dots and spaces from a component, so ``".. "``
    or ``"..."`` can act as ``..`` there. Any component made only of dots
    and spaces that holds ``..`` is refused.
    """
    return ".." in part and not part.strip(". ")


class FilePath(StringValueObject):
    """Absolute file path for media content.

    Validates that the path is:
    - Absolute (starts with / on Unix or drive letter on Windows)
    - Free of directory traversal: no ``..`` component, nor one of only
      dots and spaces that Windows trims to it (dots inside a name, as in
      a title with an ellipsis, are fine)
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

        # Use the path class that matches the path's style: PurePath on Linux
        # doesn't recognize Windows paths as absolute
        if _WINDOWS_PATH_PATTERN.match(value):
            path: PurePath = PureWindowsPath(value)
        else:
            path = PurePosixPath(value)

        # Only a parent reference climbs out of a directory. Dots inside a
        # name ("Coming... It's the End (1970).mp4") are not traversal. Split
        # the Windows way, on "/" and "\", so a backslash cannot carry a ".."
        # past the check onto a Windows host.
        if any(_is_parent_reference(part) for part in PureWindowsPath(value).parts):
            raise ValueError("FilePath cannot contain directory traversal (..)")

        if not path.is_absolute():
            raise ValueError("FilePath must be an absolute path")

        # Normalize the path (resolve redundant separators)
        return str(path)

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
