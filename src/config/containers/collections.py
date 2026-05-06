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
from src.modules.collections.infrastructure.acl import MediaLookupAdapter
from src.modules.collections.infrastructure.persistence.sqlalchemy_unit_of_work import (
    SqlAlchemyCollectionsUnitOfWorkFactory,
)


class CollectionsContainer(containers.DeclarativeContainer):  # type: ignore[misc]
    """Container for Collections bounded context dependencies.

    The ``session_factory`` and ``media_uow_factory`` dependencies must
    be wired from the parent container.
    """

    session_factory = providers.Dependency()
    # Media UoW factory comes in so the ACL adapter can open its own
    # short-lived Media transactions. Use cases only see
    # ``MediaLookupPort``.
    media_uow_factory = providers.Dependency()

    # =========================================================================
    # Unit of Work
    # =========================================================================

    collections_unit_of_work_factory = providers.Singleton(
        SqlAlchemyCollectionsUnitOfWorkFactory,
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
    # Watchlist Use Cases
    # =========================================================================

    toggle_watchlist = providers.Factory(
        ToggleWatchlistUseCase,
        uow_factory=collections_unit_of_work_factory,
    )

    get_watchlist = providers.Factory(
        GetWatchlistUseCase,
        uow_factory=collections_unit_of_work_factory,
        media_lookup=media_lookup,
    )

    check_watchlist = providers.Factory(
        CheckWatchlistUseCase,
        uow_factory=collections_unit_of_work_factory,
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
        uow_factory=collections_unit_of_work_factory,
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
        uow_factory=collections_unit_of_work_factory,
        media_lookup=media_lookup,
    )
