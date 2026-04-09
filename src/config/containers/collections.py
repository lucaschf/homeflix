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

    custom_list_repository = providers.Factory(
        SQLAlchemyCustomListRepository,
        session=session,
    )

    # =========================================================================
    # Watchlist Use Cases
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

    # =========================================================================
    # Custom List Use Cases
    # =========================================================================

    create_custom_list = providers.Factory(
        CreateCustomListUseCase,
        custom_list_repository=custom_list_repository,
    )

    list_custom_lists = providers.Factory(
        ListCustomListsUseCase,
        custom_list_repository=custom_list_repository,
    )

    rename_custom_list = providers.Factory(
        RenameCustomListUseCase,
        custom_list_repository=custom_list_repository,
    )

    delete_custom_list = providers.Factory(
        DeleteCustomListUseCase,
        custom_list_repository=custom_list_repository,
    )

    add_item_to_custom_list = providers.Factory(
        AddItemToCustomListUseCase,
        custom_list_repository=custom_list_repository,
    )

    remove_item_from_custom_list = providers.Factory(
        RemoveItemFromCustomListUseCase,
        custom_list_repository=custom_list_repository,
    )

    get_custom_list_items = providers.Factory(
        GetCustomListItemsUseCase,
        custom_list_repository=custom_list_repository,
        movie_repository=movie_repository,
        series_repository=series_repository,
    )
