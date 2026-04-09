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
from src.modules.collections.application.use_cases.get_custom_list_items import (
    GetCustomListItemsUseCase,
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
from src.modules.collections.application.use_cases.toggle_watchlist import (
    ToggleWatchlistUseCase,
)

__all__ = [
    "AddItemToCustomListUseCase",
    "CheckWatchlistUseCase",
    "CreateCustomListUseCase",
    "DeleteCustomListUseCase",
    "GetCustomListItemsUseCase",
    "GetWatchlistUseCase",
    "ListCustomListsUseCase",
    "RemoveItemFromCustomListUseCase",
    "RenameCustomListUseCase",
    "ToggleWatchlistUseCase",
]
