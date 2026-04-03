"""Shared persistence configuration.

Contains database initialization and the Base ORM model
used by all module-specific ORM models.
"""

from src.config.persistence.base import Base
from src.config.persistence.database import Database

__all__ = [
    "Base",
    "Database",
]
