"""Library bounded context dependency container.

Provides services for the Library module.
"""

from dependency_injector import containers, providers

from src.modules.library.domain.services.track_selector import TrackSelector


class LibraryContainer(containers.DeclarativeContainer):  # type: ignore[misc]
    """Container for Library bounded context dependencies.

    Provides:
    - Domain services

    A ``session`` dependency will be added here when library
    persistence is implemented, wired from InfrastructureContainer.
    """

    # =========================================================================
    # Domain Services
    # =========================================================================

    track_selector = providers.Factory(TrackSelector)
