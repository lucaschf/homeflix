"""Preferences SQLAlchemy repository exports."""

from src.modules.preferences.infrastructure.persistence.repositories.preferences_repository import (
    SQLAlchemyPreferencesRepository,
)

__all__ = ["SQLAlchemyPreferencesRepository"]
