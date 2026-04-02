"""Base domain model (re-export for backwards compatibility)."""

from src.building_blocks.domain.models import (
    DomainModel,
    SupportsUpdates,
    _raise_domain_validation,
)

__all__ = [
    "DomainModel",
    "SupportsUpdates",
    "_raise_domain_validation",
]
