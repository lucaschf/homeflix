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

from src.domain.shared.models.domain_model import DomainModel, DomainValidationError
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
    # Base classes
    "DomainModel",
    "DomainValidationError",
    "ValueObject",
    "StringValueObject",
    "IntValueObject",
    "FloatValueObject",
    "DateValueObject",
    "DomainEntity",
    "AggregateRoot",
    "ExternalId",
    # Utilities
    "utc_now",
]
