"""CatalogRequestId external ID value object."""

from typing import ClassVar

from src.building_blocks.domain.external_id import ExternalId


class CatalogRequestId(ExternalId):
    """External ID for a catalog inclusion request.

    Format: ``req_{base62_12chars}``
    Example: ``req_3yL8nQsT9mK5``
    """

    EXPECTED_PREFIX: ClassVar[str] = "req"


__all__ = ["CatalogRequestId"]
