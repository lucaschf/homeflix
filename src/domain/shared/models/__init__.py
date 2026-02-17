"""Shared domain model base classes.

Base classes and utilities for domain modeling:
- DomainModel: Base for all domain objects
- CompoundValueObject: Base for value objects with multiple fields
- StringValueObject, IntValueObject, etc.: Base for single-value wrappers
- DomainEntity: Base for entities with identity
- AggregateRoot: Base for aggregate roots
- ExternalId: Base for prefixed external IDs
- SupportsUpdates: Protocol for objects with with_updates() method

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
    ValueObject,
)

# Re-export shared value objects for convenience
from src.domain.shared.value_objects.file_path import FilePath
from src.domain.shared.value_objects.language_code import LanguageCode

__all__ = [
    "AggregateRoot",
    "CompoundValueObject",
    "DateValueObject",
    "DomainEntity",
    "DomainModel",
    "ExternalId",
    "FilePath",
    "FloatValueObject",
    "IntValueObject",
    "LanguageCode",
    "StringValueObject",
    "SupportsUpdates",
    "ValueObject",
    "utc_now",
]
