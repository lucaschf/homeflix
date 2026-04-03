"""Entity and aggregate root base classes (re-export for backwards compatibility)."""

from src.building_blocks.domain.entity import (
    AggregateRoot,
    DomainEntity,
    utc_now,
)

__all__ = [
    "AggregateRoot",
    "DomainEntity",
    "utc_now",
]
