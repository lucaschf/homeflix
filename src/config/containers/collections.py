"""Collections bounded context dependency container."""

from dependency_injector import containers, providers

from src.modules.collections.application.use_cases import (
    AddItemToCustomListUseCase,
    CheckWatchlistUseCase,
    CreateCustomListUseCase,
    DeleteCustomListUseCase,
    GetCustomListItemsUseCase,
    GetWatchlistUseCase,
    ListCustomListsUseCase,
    RemoveItemFromCustomListUseCase,
    RenameCustomListUseCase,
    ToggleWatchlistUseCase,
)
from src.modules.collections.infrastructure.persistence.repositories import (
    SQLAlchemyCustomListRepository,
    SQLAlchemyWatchlistRepository,
)
from src.modules.collections.infrastructure.persistence.sqlalchemy_unit_of_work import (
    SqlAlchemyCollectionsUnitOfWorkFactory,
)


class CollectionsContainer(containers.DeclarativeContainer):  # type: ignore[misc]
    """Container for Collections bounded context dependencies.

    The ``session``, ``session_factory``, ``movie_repository``, and
    ``series_repository`` dependencies must be wired from the parent
    container.
    """

    session = providers.Dependency()
    session_factory = providers.Dependency()
    movie_repository = providers.Dependency()
    series_repository = providers.Dependency()

    # =========================================================================
    # Repositories (read-only use cases) and Unit of Work (writes)
    # =========================================================================

    watchlist_repository = providers.Factory(
        SQLAlchemyWatchlistRepository,
        session=session,
    )

    custom_list_repository = providers.Factory(
        SQLAlchemyCustomListRepository,
        session=session,
    )

    collections_unit_of_work_factory = providers.Singleton(
        SqlAlchemyCollectionsUnitOfWorkFactory,
        session_factory=session_factory,
    )

    # =========================================================================
    # Watchlist Use Cases
    # =========================================================================

    toggle_watchlist = providers.Factory(
        ToggleWatchlistUseCase,
        uow_factory=collections_unit_of_work_factory,
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

    # =========================================================================
    # Custom List Use Cases
    # =========================================================================

    create_custom_list = providers.Factory(
        CreateCustomListUseCase,
        uow_factory=collections_unit_of_work_factory,
    )

    list_custom_lists = providers.Factory(
        ListCustomListsUseCase,
        custom_list_repository=custom_list_repository,
    )

    rename_custom_list = providers.Factory(
        RenameCustomListUseCase,
        uow_factory=collections_unit_of_work_factory,
    )

    delete_custom_list = providers.Factory(
        DeleteCustomListUseCase,
        uow_factory=collections_unit_of_work_factory,
    )

    add_item_to_custom_list = providers.Factory(
        AddItemToCustomListUseCase,
        uow_factory=collections_unit_of_work_factory,
    )

    remove_item_from_custom_list = providers.Factory(
        RemoveItemFromCustomListUseCase,
        uow_factory=collections_unit_of_work_factory,
    )

    get_custom_list_items = providers.Factory(
        GetCustomListItemsUseCase,
        custom_list_repository=custom_list_repository,
        movie_repository=movie_repository,
        series_repository=series_repository,
    )
