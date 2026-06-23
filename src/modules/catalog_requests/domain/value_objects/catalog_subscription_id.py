"""CatalogSubscriptionId external ID value object."""

from typing import ClassVar

from src.building_blocks.domain.external_id import ExternalId


class CatalogSubscriptionId(ExternalId):
    """External ID for a per-user catalog-request subscription.

    Each row is one user's opt-in to be notified when a queued title
    arrives (ADR-022). Distinct from ``CatalogRequestId`` (``req_``),
    which identifies the title in the queue rather than an interested
    user.

    Format: ``sub_{base62_12chars}``
    Example: ``sub_7pK2nQsT9mK5``
    """

    EXPECTED_PREFIX: ClassVar[str] = "sub"


__all__ = ["CatalogSubscriptionId"]
