"""Collections entities."""

from src.modules.collections.domain.entities.custom_list import (
    MAX_ITEMS_PER_LIST,
    MAX_LISTS,
    CustomList,
    CustomListItem,
)
from src.modules.collections.domain.entities.list_follow import ListFollow
from src.modules.collections.domain.entities.watchlist_item import WatchlistItem

__all__ = [
    "CustomList",
    "CustomListItem",
    "ListFollow",
    "MAX_ITEMS_PER_LIST",
    "MAX_LISTS",
    "WatchlistItem",
]
