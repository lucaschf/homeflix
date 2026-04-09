"""Custom list item external ID value object."""

from typing import ClassVar

from src.building_blocks.domain.external_id import ExternalId


class CustomListItemId(ExternalId):
    """External ID for custom list items.

    Format: cli_{base62_12chars}
    Example: cli_3yL8nQsT9mK5
    """

    EXPECTED_PREFIX: ClassVar[str] = "cli"


__all__ = ["CustomListItemId"]
