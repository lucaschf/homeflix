"""Integration events for inter-module communication.

Stable cross-BC published contracts (ADR-009). Producers publish these and
consumers subscribe to them, so neither imports the other's ``domain.events``
module. See :mod:`src.shared_kernel.integration_events.events`.
"""

from src.shared_kernel.integration_events.base import IntegrationEvent
from src.shared_kernel.integration_events.events import (
    MediaEnrichedEvent,
    MovieMergedEvent,
    MoviePromotedToSeriesEvent,
    UserDeletedEvent,
)

__all__ = [
    "IntegrationEvent",
    "MediaEnrichedEvent",
    "MovieMergedEvent",
    "MoviePromotedToSeriesEvent",
    "UserDeletedEvent",
]
