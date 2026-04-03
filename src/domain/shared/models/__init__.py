"""Shared domain model base classes (re-export for backwards compatibility)."""

from src.building_blocks.domain.entity import AggregateRoot, DomainEntity, utc_now
from src.building_blocks.domain.external_id import ExternalId
from src.building_blocks.domain.models import DomainModel, SupportsUpdates
from src.building_blocks.domain.value_objects import (
    CompoundValueObject,
    DateValueObject,
    FloatValueObject,
    IntValueObject,
    StringValueObject,
    ValueObject,
)

__all__ = [
    "AggregateRoot",
    "CompoundValueObject",
    "DateValueObject",
    "DomainEntity",
    "DomainModel",
    "ExternalId",
    "FloatValueObject",
    "IntValueObject",
    "StringValueObject",
    "SupportsUpdates",
    "ValueObject",
    "utc_now",
]
