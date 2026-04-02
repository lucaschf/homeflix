"""SQLAlchemy ORM models.

Base is defined here as shared infrastructure.
Module-specific models are re-exported for backwards compatibility
via lazy imports to avoid circular dependencies.
"""

from typing import Any

from src.infrastructure.persistence.models.base import Base


def __getattr__(name: str) -> Any:
    """Lazy import module-specific models to avoid circular imports."""
    _models = {
        "EpisodeModel": "src.modules.media.infrastructure.persistence.models.episode",
        "MovieModel": "src.modules.media.infrastructure.persistence.models.movie",
        "SeasonModel": "src.modules.media.infrastructure.persistence.models.season",
        "SeriesModel": "src.modules.media.infrastructure.persistence.models.series",
    }
    if name in _models:
        import importlib

        module = importlib.import_module(_models[name])
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "Base",
    "EpisodeModel",
    "MovieModel",
    "SeasonModel",
    "SeriesModel",
]
