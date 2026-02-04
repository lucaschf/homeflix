"""Shared domain model base classes.

Base classes and utilities for domain modeling:
- DomainModel: Base for all domain objects
- CompoundValueObject: Base for value objects with multiple fields
- StringValueObject, IntValueObject, etc.: Base for single-value wrappers
- DomainEntity: Base for entities with identity
- AggregateRoot: Base for aggregate roots
- ExternalId: Base for prefixed external IDs
- SupportsUpdates: Protocol for objects with with_updates() method

For type checking all value objects, import ValueObject directly:
    from src.domain.shared.models.value_object import ValueObject

Specific ID types (MovieId, SeriesId, etc.) are defined in their
respective bounded contexts under value_objects/.
"""

from src.domain.shared.models.domain_model import DomainModel, SupportsUpdates
from src.domain.shared.models.entity import AggregateRoot, DomainEntity, utc_now
from src.domain.shared.models.external_id import ExternalId
from src.domain.shared.models.value_object import (
    CompoundValueObject,
    DateValueObject,
    FloatValueObject,
    IntValueObject,
    StringValueObject,
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
    "utc_now",
]
