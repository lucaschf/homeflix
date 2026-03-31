"""Application building blocks: base exceptions for use cases."""

from src.building_blocks.application.errors import (
    ApplicationException,
    ForbiddenOperationException,
    ResourceNotFoundException,
    UnauthorizedOperationException,
    UseCaseValidationException,
)

__all__ = [
    "ApplicationException",
    "ForbiddenOperationException",
    "ResourceNotFoundException",
    "UnauthorizedOperationException",
    "UseCaseValidationException",
]
