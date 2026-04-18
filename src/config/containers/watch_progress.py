"""Watch Progress bounded context dependency container."""

from dependency_injector import containers, providers

from src.modules.watch_progress.application.use_cases import (
    ClearProgressUseCase,
    GetContinueWatchingUseCase,
    GetProgressUseCase,
    SaveProgressUseCase,
)
from src.modules.watch_progress.application.use_cases.clear_series_progress import (
    ClearSeriesProgressUseCase,
)
from src.modules.watch_progress.infrastructure.acl import MediaLookupAdapter
from src.modules.watch_progress.infrastructure.persistence.repositories import (
    SQLAlchemyWatchProgressRepository,
)
from src.modules.watch_progress.infrastructure.persistence.sqlalchemy_unit_of_work import (
    SqlAlchemyWatchProgressUnitOfWorkFactory,
)


class WatchProgressContainer(containers.DeclarativeContainer):  # type: ignore[misc]
    """Container for Watch Progress bounded context dependencies.

    The ``session``, ``session_factory``, ``movie_repository``, and
    ``series_repository`` dependencies must be wired from the parent
    container.
    """

    session = providers.Dependency()
    session_factory = providers.Dependency()
    # Media repositories come in so the ACL adapter can delegate
    # display lookups. Use cases only ever see ``MediaLookupPort``.
    movie_repository = providers.Dependency()
    series_repository = providers.Dependency()

    # =========================================================================
    # Repositories (read-only use cases) and Unit of Work (writes)
    # =========================================================================

    progress_repository = providers.Factory(
        SQLAlchemyWatchProgressRepository,
        session=session,
    )

    watch_progress_unit_of_work_factory = providers.Singleton(
        SqlAlchemyWatchProgressUnitOfWorkFactory,
        session_factory=session_factory,
    )

    # =========================================================================
    # Anti-corruption layer (cross-BC read ports)
    # =========================================================================

    media_lookup = providers.Factory(
        MediaLookupAdapter,
        movie_repository=movie_repository,
        series_repository=series_repository,
    )

    # =========================================================================
    # Use Cases
    # =========================================================================

    save_progress = providers.Factory(
        SaveProgressUseCase,
        uow_factory=watch_progress_unit_of_work_factory,
    )

    get_progress = providers.Factory(
        GetProgressUseCase,
        progress_repository=progress_repository,
    )

    get_continue_watching = providers.Factory(
        GetContinueWatchingUseCase,
        progress_repository=progress_repository,
        media_lookup=media_lookup,
    )

    clear_progress = providers.Factory(
        ClearProgressUseCase,
        uow_factory=watch_progress_unit_of_work_factory,
    )

    clear_series_progress = providers.Factory(
        ClearSeriesProgressUseCase,
        uow_factory=watch_progress_unit_of_work_factory,
    )
