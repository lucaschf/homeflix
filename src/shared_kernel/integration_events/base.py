"""Base class for integration events (ADR-009)."""

from dataclasses import dataclass

from src.building_blocks.domain.events import DomainEvent


@dataclass(frozen=True)
class IntegrationEvent(DomainEvent):
    """Base for stable cross-BC published contracts.

    Distinct from a bounded context's internal domain events: an
    integration event is the *published* shape other BCs subscribe to,
    so it lives in ``shared_kernel`` and neither producer nor consumer
    imports the other's internals (ADR-009). Subclasses ``DomainEvent``
    so the in-process event bus — which dispatches by exact concrete
    type — handles it unchanged.
    """
