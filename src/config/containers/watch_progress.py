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
from src.modules.watch_progress.infrastructure.persistence.sqlalchemy_unit_of_work import (
    SqlAlchemyWatchProgressUnitOfWorkFactory,
)


class WatchProgressContainer(containers.DeclarativeContainer):
    """Container for Watch Progress bounded context dependencies.

    The ``session_factory`` and ``media_uow_factory`` dependencies
    must be wired from the parent container.
    """

    session_factory = providers.Dependency()
    # Media UoW factory comes in so the ACL adapter can open its own
    # short-lived Media transactions. Use cases only see
    # ``MediaLookupPort``.
    media_uow_factory = providers.Dependency()

    # =========================================================================
    # Unit of Work
    # =========================================================================

    watch_progress_unit_of_work_factory = providers.Singleton(
        SqlAlchemyWatchProgressUnitOfWorkFactory,
        session_factory=session_factory,
    )

    # =========================================================================
    # Anti-corruption layer (cross-BC read ports)
    # =========================================================================

    media_lookup = providers.Factory(
        MediaLookupAdapter,
        media_uow_factory=media_uow_factory,
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
        uow_factory=watch_progress_unit_of_work_factory,
    )

    get_continue_watching = providers.Factory(
        GetContinueWatchingUseCase,
        uow_factory=watch_progress_unit_of_work_factory,
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
