"""Value object base classes (re-export for backwards compatibility)."""

from src.building_blocks.domain.value_objects import (
    CompoundValueObject,
    DateValueObject,
    FloatValueObject,
    IntValueObject,
    StringValueObject,
    ValueObject,
)

__all__ = [
    "CompoundValueObject",
    "DateValueObject",
    "FloatValueObject",
    "IntValueObject",
    "StringValueObject",
    "ValueObject",
]
