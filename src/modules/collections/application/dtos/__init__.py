"""Collections DTOs."""

from src.modules.collections.application.dtos.custom_list_dtos import (
    AddItemToCustomListInput,
    CreateCustomListInput,
    CustomListItemOutput,
    CustomListOutput,
    DeleteCustomListInput,
    GetCustomListItemsInput,
    RemoveItemFromCustomListInput,
    RenameCustomListInput,
    ReorderCustomListItemsInput,
)
from src.modules.collections.application.dtos.watchlist_dtos import (
    CheckWatchlistInput,
    GetWatchlistInput,
    ToggleWatchlistInput,
    ToggleWatchlistOutput,
    WatchlistItemOutput,
)

__all__ = [
    "AddItemToCustomListInput",
    "CheckWatchlistInput",
    "CreateCustomListInput",
    "CustomListItemOutput",
    "CustomListOutput",
    "DeleteCustomListInput",
    "GetCustomListItemsInput",
    "GetWatchlistInput",
    "RemoveItemFromCustomListInput",
    "RenameCustomListInput",
    "ReorderCustomListItemsInput",
    "ToggleWatchlistInput",
    "ToggleWatchlistOutput",
    "WatchlistItemOutput",
]
