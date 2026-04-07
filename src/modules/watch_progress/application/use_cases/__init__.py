"""Watch Progress use cases."""

from src.modules.watch_progress.application.use_cases.clear_progress import (
    ClearProgressUseCase,
)
from src.modules.watch_progress.application.use_cases.get_continue_watching import (
    GetContinueWatchingUseCase,
)
from src.modules.watch_progress.application.use_cases.get_progress import (
    GetProgressUseCase,
)
from src.modules.watch_progress.application.use_cases.save_progress import (
    SaveProgressUseCase,
)

__all__ = [
    "ClearProgressUseCase",
    "GetContinueWatchingUseCase",
    "GetProgressUseCase",
    "SaveProgressUseCase",
]
