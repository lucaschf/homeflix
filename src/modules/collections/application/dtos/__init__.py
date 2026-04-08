"""Collections DTOs."""

from src.modules.collections.application.dtos.custom_list_dtos import (
    AddItemToCustomListInput,
    CreateCustomListInput,
    CustomListItemOutput,
    CustomListOutput,
    GetCustomListItemsInput,
    RemoveItemFromCustomListInput,
    RenameCustomListInput,
)
from src.modules.collections.application.dtos.watchlist_dtos import (
    GetWatchlistInput,
    ToggleWatchlistInput,
    ToggleWatchlistOutput,
    WatchlistItemOutput,
)

__all__ = [
    "AddItemToCustomListInput",
    "CreateCustomListInput",
    "CustomListItemOutput",
    "CustomListOutput",
    "GetCustomListItemsInput",
    "GetWatchlistInput",
    "RemoveItemFromCustomListInput",
    "RenameCustomListInput",
    "ToggleWatchlistInput",
    "ToggleWatchlistOutput",
    "WatchlistItemOutput",
]
