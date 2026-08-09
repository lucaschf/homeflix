"""Collections use cases."""

from src.modules.collections.application.use_cases.add_item_to_custom_list import (
    AddItemToCustomListUseCase,
)
from src.modules.collections.application.use_cases.check_watchlist import (
    CheckWatchlistUseCase,
)
from src.modules.collections.application.use_cases.create_custom_list import (
    CreateCustomListUseCase,
)
from src.modules.collections.application.use_cases.delete_custom_list import (
    DeleteCustomListUseCase,
)
from src.modules.collections.application.use_cases.follow_shared_list import (
    FollowSharedListUseCase,
)
from src.modules.collections.application.use_cases.get_custom_list_items import (
    GetCustomListItemsUseCase,
)
from src.modules.collections.application.use_cases.get_shared_list_preview import (
    GetSharedListPreviewUseCase,
)
from src.modules.collections.application.use_cases.get_watchlist import (
    GetWatchlistUseCase,
)
from src.modules.collections.application.use_cases.list_custom_lists import (
    ListCustomListsUseCase,
)
from src.modules.collections.application.use_cases.remove_item_from_custom_list import (
    RemoveItemFromCustomListUseCase,
)
from src.modules.collections.application.use_cases.rename_custom_list import (
    RenameCustomListUseCase,
)
from src.modules.collections.application.use_cases.reorder_custom_list_items import (
    ReorderCustomListItemsUseCase,
)
from src.modules.collections.application.use_cases.revoke_custom_list_share import (
    RevokeCustomListShareUseCase,
)
from src.modules.collections.application.use_cases.share_custom_list import (
    ShareCustomListUseCase,
)
from src.modules.collections.application.use_cases.toggle_watchlist import (
    ToggleWatchlistUseCase,
)
from src.modules.collections.application.use_cases.unfollow_custom_list import (
    UnfollowCustomListUseCase,
)

__all__ = [
    "AddItemToCustomListUseCase",
    "CheckWatchlistUseCase",
    "CreateCustomListUseCase",
    "DeleteCustomListUseCase",
    "FollowSharedListUseCase",
    "GetCustomListItemsUseCase",
    "GetSharedListPreviewUseCase",
    "GetWatchlistUseCase",
    "ListCustomListsUseCase",
    "RemoveItemFromCustomListUseCase",
    "RenameCustomListUseCase",
    "ReorderCustomListItemsUseCase",
    "RevokeCustomListShareUseCase",
    "ShareCustomListUseCase",
    "ToggleWatchlistUseCase",
    "UnfollowCustomListUseCase",
]
