"""Library external ID value object."""

from typing import ClassVar

from pydantic import model_validator

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

    @model_validator(mode="after")
    def validate_prefix(self) -> "LibraryId":
        """Ensure the ID has the correct prefix."""
        if self.prefix != self.EXPECTED_PREFIX:
            raise ValueError(f"LibraryId must have '{self.EXPECTED_PREFIX}' prefix")
        return self

    @classmethod
    def generate(cls) -> "LibraryId":
        """Generate a new LibraryId.

        Returns:
            A new LibraryId with a unique base62 suffix.
        """
        base = cls._generate_with_prefix(cls.EXPECTED_PREFIX)
        return cls(base.value)


__all__ = ["LibraryId"]
