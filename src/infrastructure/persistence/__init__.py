"""Shared persistence layer.

Contains database initialization and the Base ORM model.
Module-specific models, repositories, and mappers live in their
respective module packages (e.g., src.modules.media.infrastructure).
"""

from src.infrastructure.persistence.database import Database
from src.infrastructure.persistence.models.base import Base

__all__ = [
    "Base",
    "Database",
]
