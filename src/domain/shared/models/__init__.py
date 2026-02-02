"""Shared domain model base classes.

Base classes and utilities for domain modeling:
- DomainModel: Base for all domain objects
- ValueObject: Base for immutable value objects
- DomainEntity: Base for entities with identity
- AggregateRoot: Base for aggregate roots
- ExternalId: Base for prefixed external IDs

Specific ID types (MovieId, SeriesId, etc.) are defined in their
respective bounded contexts under value_objects/.
"""

from src.domain.shared.models.domain_model import DomainModel
from src.domain.shared.models.entity import AggregateRoot, DomainEntity, utc_now
from src.domain.shared.models.external_id import ExternalId
from src.domain.shared.models.value_object import (
    DateValueObject,
    FloatValueObject,
    IntValueObject,
    StringValueObject,
    ValueObject,
)

__all__ = [
    "AggregateRoot",
    "DateValueObject",
    "DomainEntity",
    # Base classes
    "DomainModel",
    "ExternalId",
    "FloatValueObject",
    "IntValueObject",
    "StringValueObject",
    "ValueObject",
    # Utilities
    "utc_now",
]
