"""Watch Progress bounded context dependency container."""

from typing import Any

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
from src.modules.watch_progress.infrastructure.acl import (
    MediaLookupAdapter,
    ProfileViewingPolicyAdapter,
)
from src.modules.watch_progress.infrastructure.persistence.sqlalchemy_unit_of_work import (
    SqlAlchemyWatchProgressUnitOfWorkFactory,
)


class WatchProgressContainer(containers.DeclarativeContainer):
    """Container for Watch Progress bounded context dependencies.

    The ``session_factory``, ``media_uow_factory`` and
    ``identity_uow_factory`` dependencies must be wired from the parent
    container.
    """

    session_factory = providers.Dependency[Any]()
    # Media UoW factory comes in so the ACL adapter can open its own
    # short-lived Media transactions. Use cases only see
    # ``MediaLookupPort``.
    media_uow_factory = providers.Dependency[Any]()
    # Identity UoW factory — the profile ACL adapter opens its own
    # short-lived Identity transactions to resolve the caller's viewing
    # policy. Use cases only see ``ProfileViewingPolicyPort``.
    identity_uow_factory = providers.Dependency[Any]()

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

    profile_viewing_policy = providers.Factory(
        ProfileViewingPolicyAdapter,
        identity_uow_factory=identity_uow_factory,
    )

    # =========================================================================
    # Use Cases
    # =========================================================================

    save_progress = providers.Factory(
        SaveProgressUseCase,
        uow_factory=watch_progress_unit_of_work_factory,
        media_lookup=media_lookup,
        profile_viewing_policy=profile_viewing_policy,
    )

    get_progress = providers.Factory(
        GetProgressUseCase,
        uow_factory=watch_progress_unit_of_work_factory,
        media_lookup=media_lookup,
        profile_viewing_policy=profile_viewing_policy,
    )

    get_continue_watching = providers.Factory(
        GetContinueWatchingUseCase,
        uow_factory=watch_progress_unit_of_work_factory,
        media_lookup=media_lookup,
        profile_viewing_policy=profile_viewing_policy,
    )

    clear_progress = providers.Factory(
        ClearProgressUseCase,
        uow_factory=watch_progress_unit_of_work_factory,
    )

    clear_series_progress = providers.Factory(
        ClearSeriesProgressUseCase,
        uow_factory=watch_progress_unit_of_work_factory,
    )
