"""GetProgressUseCase - Get watch progress for a media item."""

from src.modules.watch_progress.application.dtos import GetProgressInput, ProgressOutput
from src.modules.watch_progress.application.unit_of_work import WatchProgressUnitOfWorkFactory
from src.modules.watch_progress.domain.value_objects import WatchableMediaId
from src.shared_kernel.value_objects.profile_id import ProfileId


class GetProgressUseCase:
    """Retrieve watch progress for a single media item, scoped to one profile.

    Returns ``None`` if the profile has no progress record for the
    media — does not raise 404. Other profiles' rows are never
    visible.
    """

    def __init__(self, uow_factory: WatchProgressUnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def execute(self, input_dto: GetProgressInput) -> ProgressOutput | None:
        """Return the caller's progress for the media, or ``None`` if absent."""
        async with self._uow_factory() as uow:
            progress = await uow.progress.find_by_media_id(
                WatchableMediaId(input_dto.media_id),
                ProfileId(input_dto.profile_id),
            )
        if progress is None:
            return None
        return ProgressOutput.from_entity(progress)


__all__ = ["GetProgressUseCase"]
