"""Library bounded context dependency container.

Provides repositories and services for the Library module.
"""

from dependency_injector import containers, providers

from src.modules.library.domain.services.track_selector import TrackSelector


class LibraryContainer(containers.DeclarativeContainer):  # type: ignore[misc]
    """Container for Library bounded context dependencies.

    Provides:
    - Domain services
    - Repository implementations (when infrastructure is added)

    Example:
        >>> container = LibraryContainer()
        >>> selector = container.track_selector()
    """

    # Database session provided by parent container (for future use)
    session = providers.Dependency(default=None)

    # =========================================================================
    # Domain Services
    # =========================================================================

    track_selector = providers.Factory(TrackSelector)
