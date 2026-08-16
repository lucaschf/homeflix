"""Collections bounded context dependency container."""

from dependency_injector import containers, providers

from src.modules.collections.application.use_cases import (
    AddItemToCustomListUseCase,
    CheckWatchlistUseCase,
    CreateCustomListUseCase,
    DeleteCustomListUseCase,
    FollowSharedListUseCase,
    GetCustomListItemsUseCase,
    GetSharedListPreviewUseCase,
    GetWatchlistUseCase,
    ListCustomListsUseCase,
    RemoveItemFromCustomListUseCase,
    RenameCustomListUseCase,
    ReorderCustomListItemsUseCase,
    RevokeCustomListShareUseCase,
    ShareCustomListUseCase,
    ToggleWatchlistUseCase,
    UnfollowCustomListUseCase,
)
from src.modules.collections.infrastructure.acl import (
    MediaLookupAdapter,
    ProfileLibraryAccessAdapter,
    ProfileLookupAdapter,
    ProgressLookupAdapter,
)
from src.modules.collections.infrastructure.persistence.sqlalchemy_unit_of_work import (
    SqlAlchemyCollectionsUnitOfWorkFactory,
)


class CollectionsContainer(containers.DeclarativeContainer):
    """Container for Collections bounded context dependencies.

    The ``session_factory``, ``media_uow_factory`` and
    ``watch_progress_uow_factory`` dependencies must be wired from the
    parent container.
    """

    session_factory = providers.Dependency()
    # Media UoW factory comes in so the ACL adapter can open its own
    # short-lived Media transactions. Use cases only see
    # ``MediaLookupPort``.
    media_uow_factory = providers.Dependency()
    # Watch Progress UoW factory — the progress ACL adapter opens its
    # own short-lived transactions. Use cases only see
    # ``ProgressLookupPort``.
    watch_progress_uow_factory = providers.Dependency()
    # Identity UoW factory — the profile ACL adapters open their own
    # short-lived Identity transactions to resolve a follower's library
    # access and an owner's display name. Use cases only see the
    # ``ProfileLibraryAccessPort`` / ``ProfileLookupPort`` abstractions.
    identity_uow_factory = providers.Dependency()

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

    progress_lookup = providers.Factory(
        ProgressLookupAdapter,
        watch_progress_uow_factory=watch_progress_uow_factory,
    )

    profile_library_access = providers.Factory(
        ProfileLibraryAccessAdapter,
        identity_uow_factory=identity_uow_factory,
    )

    profile_lookup = providers.Factory(
        ProfileLookupAdapter,
        identity_uow_factory=identity_uow_factory,
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
        progress_lookup=progress_lookup,
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
        profile_lookup=profile_lookup,
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

    reorder_custom_list_items = providers.Factory(
        ReorderCustomListItemsUseCase,
        uow_factory=collections_unit_of_work_factory,
    )

    get_custom_list_items = providers.Factory(
        GetCustomListItemsUseCase,
        uow_factory=collections_unit_of_work_factory,
        media_lookup=media_lookup,
        progress_lookup=progress_lookup,
        profile_library_access=profile_library_access,
    )

    # =========================================================================
    # Share / Follow Use Cases
    # =========================================================================

    share_custom_list = providers.Factory(
        ShareCustomListUseCase,
        uow_factory=collections_unit_of_work_factory,
    )

    revoke_custom_list_share = providers.Factory(
        RevokeCustomListShareUseCase,
        uow_factory=collections_unit_of_work_factory,
    )

    get_shared_list_preview = providers.Factory(
        GetSharedListPreviewUseCase,
        uow_factory=collections_unit_of_work_factory,
        media_lookup=media_lookup,
        progress_lookup=progress_lookup,
        profile_library_access=profile_library_access,
        profile_lookup=profile_lookup,
    )

    follow_shared_list = providers.Factory(
        FollowSharedListUseCase,
        uow_factory=collections_unit_of_work_factory,
    )

    unfollow_custom_list = providers.Factory(
        UnfollowCustomListUseCase,
        uow_factory=collections_unit_of_work_factory,
    )
