"""Library external ID value object."""

from typing import ClassVar

from src.domain.shared.models.external_id import ExternalId


class LibraryId(ExternalId):
    """External ID for libraries.

    Format: lib_{base62_12chars}
    Example: lib_2xK9mPqR7nL4

    Example:
        >>> library_id = LibraryId.generate()
        >>> library_id.prefix
        'lib'
        >>> LibraryId("lib_2xK9mPqR7nL4")
        LibraryId('lib_2xK9mPqR7nL4')
    """

    EXPECTED_PREFIX: ClassVar[str] = "lib"


__all__ = ["LibraryId"]
