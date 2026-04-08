"""List external ID value object."""

from typing import ClassVar

from src.building_blocks.domain.external_id import ExternalId


class ListId(ExternalId):
    """External ID for watchlist items.

    Format: lst_{base62_12chars}
    Example: lst_3yL8nQsT9mK5
    """

    EXPECTED_PREFIX: ClassVar[str] = "lst"


__all__ = ["ListId"]
