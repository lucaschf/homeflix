"""Application layer exceptions (re-export for backwards compatibility)."""

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
