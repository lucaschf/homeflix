"""Collections bounded context dependency container."""

from dependency_injector import containers, providers

from src.modules.collections.application.use_cases import (
    CheckWatchlistUseCase,
    GetWatchlistUseCase,
    ToggleWatchlistUseCase,
)
from src.modules.collections.infrastructure.persistence.repositories import (
    SQLAlchemyWatchlistRepository,
)


class CollectionsContainer(containers.DeclarativeContainer):  # type: ignore[misc]
    """Container for Collections bounded context dependencies.

    The ``session``, ``movie_repository``, and ``series_repository``
    dependencies must be wired from the parent container.
    """

    session = providers.Dependency()
    movie_repository = providers.Dependency()
    series_repository = providers.Dependency()

    # =========================================================================
    # Repositories
    # =========================================================================

    watchlist_repository = providers.Factory(
        SQLAlchemyWatchlistRepository,
        session=session,
    )

    # =========================================================================
    # Use Cases
    # =========================================================================

    toggle_watchlist = providers.Factory(
        ToggleWatchlistUseCase,
        watchlist_repository=watchlist_repository,
    )

    get_watchlist = providers.Factory(
        GetWatchlistUseCase,
        watchlist_repository=watchlist_repository,
        movie_repository=movie_repository,
        series_repository=series_repository,
    )

    check_watchlist = providers.Factory(
        CheckWatchlistUseCase,
        watchlist_repository=watchlist_repository,
    )
