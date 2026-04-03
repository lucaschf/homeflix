"""Media domain external IDs.

Typed external IDs for the Media bounded context:
- MovieId (mov_xxx)
- SeriesId (ser_xxx)
- SeasonId (ssn_xxx)
- EpisodeId (epi_xxx)
"""

from typing import ClassVar

from src.building_blocks.domain.errors import DomainValidationException
from src.building_blocks.domain.external_id import ExternalId
from src.modules.media.domain.rule_codes import MediaRuleCodes


class MovieId(ExternalId):
    """External ID for movies.

    Format: mov_{base62_12chars}
    Example: mov_2xK9mPqR7nL4
    """

    EXPECTED_PREFIX: ClassVar[str] = "mov"


class SeriesId(ExternalId):
    """External ID for TV series.

    Format: ser_{base62_12chars}
    Example: ser_3yL8nQsT9mK5
    """

    EXPECTED_PREFIX: ClassVar[str] = "ser"


class SeasonId(ExternalId):
    """External ID for seasons.

    Format: ssn_{base62_12chars}
    Example: ssn_4zM9oPtU0nL6
    """

    EXPECTED_PREFIX: ClassVar[str] = "ssn"


class EpisodeId(ExternalId):
    """External ID for episodes.

    Format: epi_{base62_12chars}
    Example: epi_5aH0pQuV1oM7
    """

    EXPECTED_PREFIX: ClassVar[str] = "epi"


# Type alias for any media ID
MediaId = MovieId | SeriesId | SeasonId | EpisodeId


def parse_media_id(value: str) -> MediaId:
    """Parse a string into the appropriate MediaId type.

    Args:
        value: The external ID string to parse.

    Returns:
        The typed MediaId (MovieId, SeriesId, SeasonId, or EpisodeId).

    Raises:
        DomainValidationException: If the format is invalid or prefix is unknown.

    Example:
        >>> parse_media_id("mov_2xK9mPqR7nL4")
        MovieId('mov_2xK9mPqR7nL4')
    """
    if not value or "_" not in value:
        raise DomainValidationException(
            message=f"Invalid media ID format: {value}",
            message_code=MediaRuleCodes.INVALID_MEDIA_ID_FORMAT,
            object_type="MediaId",
        )

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
            raise DomainValidationException(
                message=f"Unknown media prefix '{prefix}'",
                message_code=MediaRuleCodes.UNKNOWN_MEDIA_PREFIX,
                object_type="MediaId",
            )


__all__ = [
    "EpisodeId",
    "MediaId",
    "MovieId",
    "SeasonId",
    "SeriesId",
    "parse_media_id",
]
