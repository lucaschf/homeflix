"""Watch Progress bounded context dependency container."""

from dependency_injector import containers, providers

from src.modules.watch_progress.application.use_cases import (
    ClearProgressUseCase,
    GetContinueWatchingUseCase,
    GetProgressUseCase,
    SaveProgressUseCase,
)
from src.modules.watch_progress.infrastructure.persistence.repositories import (
    SQLAlchemyWatchProgressRepository,
)


class WatchProgressContainer(containers.DeclarativeContainer):  # type: ignore[misc]
    """Container for Watch Progress bounded context dependencies.

    The ``session`` and ``movie_repository`` dependencies must be
    wired from the parent container.
    """

    session = providers.Dependency()
    movie_repository = providers.Dependency()
    series_repository = providers.Dependency()

    # =========================================================================
    # Repositories
    # =========================================================================

    progress_repository = providers.Factory(
        SQLAlchemyWatchProgressRepository,
        session=session,
    )

    # =========================================================================
    # Use Cases
    # =========================================================================

    save_progress = providers.Factory(
        SaveProgressUseCase,
        progress_repository=progress_repository,
    )

    get_progress = providers.Factory(
        GetProgressUseCase,
        progress_repository=progress_repository,
    )

    get_continue_watching = providers.Factory(
        GetContinueWatchingUseCase,
        progress_repository=progress_repository,
        movie_repository=movie_repository,
        series_repository=series_repository,
    )

    clear_progress = providers.Factory(
        ClearProgressUseCase,
        progress_repository=progress_repository,
    )
