"""Collections use cases."""

from src.modules.collections.application.use_cases.check_watchlist import (
    CheckWatchlistUseCase,
)
from src.modules.collections.application.use_cases.get_watchlist import (
    GetWatchlistUseCase,
)
from src.modules.collections.application.use_cases.toggle_watchlist import (
    ToggleWatchlistUseCase,
)

__all__ = [
    "CheckWatchlistUseCase",
    "GetWatchlistUseCase",
    "ToggleWatchlistUseCase",
]
