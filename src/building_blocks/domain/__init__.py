"""Domain building blocks: base models, value objects, entities, and errors."""

from src.building_blocks.domain.aggregate_root import AggregateRoot
from src.building_blocks.domain.entity import DomainEntity, utc_now
from src.building_blocks.domain.errors import (
    BusinessRuleViolationException,
    CoreException,
    DomainConflictException,
    DomainException,
    DomainNotFoundException,
    DomainValidationException,
    ExceptionDetail,
    Severity,
)
from src.building_blocks.domain.events import DomainEvent, MediaCreatedEvent
from src.building_blocks.domain.external_id import (
    BASE62_ALPHABET,
    RANDOM_PART_LENGTH,
    ExternalId,
)
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
    "BASE62_ALPHABET",
    "BusinessRuleViolationException",
    "CompoundValueObject",
    "CoreException",
    "DateValueObject",
    "DomainConflictException",
    "DomainEntity",
    "DomainEvent",
    "DomainException",
    "DomainModel",
    "DomainNotFoundException",
    "DomainValidationException",
    "ExceptionDetail",
    "ExternalId",
    "FloatValueObject",
    "IntValueObject",
    "MediaCreatedEvent",
    "RANDOM_PART_LENGTH",
    "Severity",
    "StringValueObject",
    "SupportsUpdates",
    "ValueObject",
    "utc_now",
]
