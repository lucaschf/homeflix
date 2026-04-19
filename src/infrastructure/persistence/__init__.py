"""Shared persistence configuration.

Contains database initialization and the Base ORM model
used by all module-specific ORM models.
"""

from .base import Base
from .database import Database

__all__ = [
    "Base",
    "Database",
]
