"""Media domain external IDs.

Typed external IDs for the Media bounded context:
- MovieId (mov_xxx)
- SeriesId (ser_xxx)
- SeasonId (ssn_xxx)
- EpisodeId (epi_xxx)
"""

from typing import ClassVar

from pydantic import model_validator

from src.domain.shared.models.external_id import ExternalId


class MovieId(ExternalId):
    """External ID for movies.

    Format: mov_{base62_12chars}
    Example: mov_2xK9mPqR7nL4
    """

    EXPECTED_PREFIX: ClassVar[str] = "mov"

    @model_validator(mode="after")
    def validate_prefix(self) -> "MovieId":
        """Ensure the ID has the correct prefix."""
        if self.prefix != self.EXPECTED_PREFIX:
            raise ValueError(f"MovieId must have '{self.EXPECTED_PREFIX}' prefix")
        return self

    @classmethod
    def generate(cls) -> "MovieId":
        """Generate a new MovieId."""
        base = cls._generate_with_prefix(cls.EXPECTED_PREFIX)
        return cls(base.value)


class SeriesId(ExternalId):
    """External ID for TV series.

    Format: ser_{base62_12chars}
    Example: ser_3yL8nQsT9mK5
    """

    EXPECTED_PREFIX: ClassVar[str] = "ser"

    @model_validator(mode="after")
    def validate_prefix(self) -> "SeriesId":
        """Ensure the ID has the correct prefix."""
        if self.prefix != self.EXPECTED_PREFIX:
            raise ValueError(f"SeriesId must have '{self.EXPECTED_PREFIX}' prefix")
        return self

    @classmethod
    def generate(cls) -> "SeriesId":
        """Generate a new SeriesId."""
        base = cls._generate_with_prefix(cls.EXPECTED_PREFIX)
        return cls(base.value)


class SeasonId(ExternalId):
    """External ID for seasons.

    Format: ssn_{base62_12chars}
    Example: ssn_4zM9oPtU0nL6
    """

    EXPECTED_PREFIX: ClassVar[str] = "ssn"

    @model_validator(mode="after")
    def validate_prefix(self) -> "SeasonId":
        """Ensure the ID has the correct prefix."""
        if self.prefix != self.EXPECTED_PREFIX:
            raise ValueError(f"SeasonId must have '{self.EXPECTED_PREFIX}' prefix")
        return self

    @classmethod
    def generate(cls) -> "SeasonId":
        """Generate a new SeasonId."""
        base = cls._generate_with_prefix(cls.EXPECTED_PREFIX)
        return cls(base.value)


class EpisodeId(ExternalId):
    """External ID for episodes.

    Format: epi_{base62_12chars}
    Example: epi_5aH0pQuV1oM7
    """

    EXPECTED_PREFIX: ClassVar[str] = "epi"

    @model_validator(mode="after")
    def validate_prefix(self) -> "EpisodeId":
        """Ensure the ID has the correct prefix."""
        if self.prefix != self.EXPECTED_PREFIX:
            raise ValueError(f"EpisodeId must have '{self.EXPECTED_PREFIX}' prefix")
        return self

    @classmethod
    def generate(cls) -> "EpisodeId":
        """Generate a new EpisodeId."""
        base = cls._generate_with_prefix(cls.EXPECTED_PREFIX)
        return cls(base.value)


# Type alias for any media ID
MediaId = MovieId | SeriesId | SeasonId | EpisodeId


def parse_media_id(value: str) -> MediaId:
    """Parse a string into the appropriate MediaId type.

    Args:
        value: The external ID string to parse.

    Returns:
        The typed MediaId (MovieId, SeriesId, SeasonId, or EpisodeId).

    Raises:
        ValueError: If the format is invalid or prefix is unknown.

    Example:
        >>> parse_media_id("mov_2xK9mPqR7nL4")
        MovieId('mov_2xK9mPqR7nL4')
    """
    if not value or "_" not in value:
        raise ValueError(f"Invalid media ID format: {value}")

    prefix = value.split("_")[0]

    match prefix:
        case "mov":
            return MovieId(value)
        case "ser":
            return SeriesId(value)
        case "ssn":
            return SeasonId(value)
        case "epi":
            return EpisodeId(value)
        case _:
            raise ValueError(f"Unknown media prefix '{prefix}'")


__all__ = [
    "EpisodeId",
    "MediaId",
    "MovieId",
    "SeasonId",
    "SeriesId",
    "parse_media_id",
]
