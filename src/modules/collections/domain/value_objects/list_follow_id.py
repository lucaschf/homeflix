"""ListFollow external ID value object."""

from typing import ClassVar

from src.building_blocks.domain.external_id import ExternalId


class ListFollowId(ExternalId):
    """External ID for a follow of a shared custom list.

    Format: lfw_{base62_12chars}
    Example: lfw_3yL8nQsT9mK5
    """

    EXPECTED_PREFIX: ClassVar[str] = "lfw"


__all__ = ["ListFollowId"]
