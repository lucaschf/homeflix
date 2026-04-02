"""Domain shared exceptions (re-export for backwards compatibility)."""

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

__all__ = [
    "BusinessRuleViolationException",
    "CoreException",
    "DomainConflictException",
    "DomainException",
    "DomainNotFoundException",
    "DomainValidationException",
    "ExceptionDetail",
    "Severity",
]
