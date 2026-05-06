"""ClearProgressUseCase - Clear watch progress for a media item."""

from dataclasses import dataclass

from src.modules.watch_progress.application.unit_of_work import (
    WatchProgressUnitOfWorkFactory,
)
from src.shared_kernel.value_objects.profile_id import ProfileId


@dataclass(frozen=True)
class ClearProgressInput:
    """Input for ClearProgressUseCase."""

    profile_id: str
    media_id: str


class ClearProgressUseCase:
    """Clear (soft-delete) watch progress for a media item in one profile."""

    def __init__(self, uow_factory: WatchProgressUnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def execute(self, input_dto: ClearProgressInput) -> bool:
        """Soft-delete the row, returning ``True`` when one was found."""
        async with self._uow_factory() as uow:
            return await uow.progress.delete(
                input_dto.media_id,
                ProfileId(input_dto.profile_id),
            )


__all__ = ["ClearProgressInput", "ClearProgressUseCase"]
