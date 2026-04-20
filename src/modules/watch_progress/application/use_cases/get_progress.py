"""GetProgressUseCase - Get watch progress for a media item."""

from src.modules.watch_progress.application.dtos import GetProgressInput, ProgressOutput
from src.modules.watch_progress.application.unit_of_work import WatchProgressUnitOfWorkFactory


class GetProgressUseCase:
    """Retrieve watch progress for a single media item.

    Returns None if no progress exists (does not raise 404).

    Example:
        >>> use_case = GetProgressUseCase(uow_factory)
        >>> result = await use_case.execute(GetProgressInput("mov_abc123def456"))
    """

    def __init__(self, uow_factory: WatchProgressUnitOfWorkFactory) -> None:
        """Initialize the use case.

        Args:
            uow_factory: Factory that opens a fresh watch progress UoW.
        """
        self._uow_factory = uow_factory

    async def execute(self, input_dto: GetProgressInput) -> ProgressOutput | None:
        """Execute the use case.

        Args:
            input_dto: Contains the media_id to look up.

        Returns:
            ProgressOutput if found, None otherwise.
        """
        async with self._uow_factory() as uow:
            progress = await uow.progress.find_by_media_id(input_dto.media_id)
        if progress is None:
            return None
        return ProgressOutput.from_entity(progress)


__all__ = ["GetProgressUseCase"]
