"""ClearProgressUseCase - Clear watch progress for a media item."""

from dataclasses import dataclass

from src.modules.watch_progress.application.unit_of_work import (
    WatchProgressUnitOfWorkFactory,
)


@dataclass(frozen=True)
class ClearProgressInput:
    """Input for ClearProgressUseCase.

    Attributes:
        media_id: External ID of the media.
    """

    media_id: str


class ClearProgressUseCase:
    """Clear (soft-delete) watch progress for a media item."""

    def __init__(self, uow_factory: WatchProgressUnitOfWorkFactory) -> None:
        """Initialize the use case.

        Args:
            uow_factory: Factory that opens a fresh watch progress UoW.
        """
        self._uow_factory = uow_factory

    async def execute(self, input_dto: ClearProgressInput) -> bool:
        """Execute the use case.

        Args:
            input_dto: Contains the media_id to clear.

        Returns:
            True if progress was found and deleted, False otherwise.
        """
        async with self._uow_factory() as uow:
            return await uow.progress.delete(input_dto.media_id)


__all__ = ["ClearProgressUseCase"]
