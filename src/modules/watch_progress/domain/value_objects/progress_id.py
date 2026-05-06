"""Progress external ID value object."""

from typing import ClassVar

from src.building_blocks.domain.external_id import ExternalId


class ProgressId(ExternalId):
    """External ID for watch progress records.

    Format: prg_{base62_12chars}
    Example: prg_3yL8nQsT9mK5
    """

    EXPECTED_PREFIX: ClassVar[str] = "prg"


__all__ = ["ProgressId"]
