"""NotificationId external ID value object."""

from typing import ClassVar

from src.building_blocks.domain.external_id import ExternalId


class NotificationId(ExternalId):
    """External ID for an in-app notification row.

    Format: ``nfy_{base62_12chars}``
    Example: ``nfy_3yL8nQsT9mK5``
    """

    EXPECTED_PREFIX: ClassVar[str] = "nfy"


__all__ = ["NotificationId"]
