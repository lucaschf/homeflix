"""Base exception classes (re-export for backwards compatibility)."""

from src.building_blocks.domain.errors import (
    CoreException,
    ExceptionDetail,
    Severity,
)

__all__ = [
    "CoreException",
    "ExceptionDetail",
    "Severity",
]
