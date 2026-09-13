"""GetProgressUseCase - Get watch progress for a media item."""

from src.modules.watch_progress.application.dtos import GetProgressInput, ProgressOutput
from src.modules.watch_progress.application.ports import (
    MediaLookupPort,
    ProfileViewingPolicyPort,
)
from src.modules.watch_progress.application.unit_of_work import WatchProgressUnitOfWorkFactory
from src.modules.watch_progress.application.use_cases._title_gate import (
    is_title_visible,
    title_of,
)
from src.modules.watch_progress.domain.value_objects import WatchableMediaId
from src.shared_kernel.value_objects.profile_id import ProfileId


class GetProgressUseCase:
    """Retrieve watch progress for a single media item, scoped to one profile.

    Returns ``None`` if the profile has no progress record for the
    media — does not raise 404. Other profiles' rows are never
    visible. A row on a title the profile can no longer see is answered
    the same way, as absent, so a row recorded before a restriction
    reveals nothing about the title.
    """

    def __init__(
        self,
        uow_factory: WatchProgressUnitOfWorkFactory,
        media_lookup: MediaLookupPort,
        profile_viewing_policy: ProfileViewingPolicyPort,
    ) -> None:
        """Initialize the use case.

        Args:
            uow_factory: Factory that opens a fresh watch progress UoW.
            media_lookup: Port for asking the catalog which titles are visible.
            profile_viewing_policy: Port resolving the caller's viewing policy.
        """
        self._uow_factory = uow_factory
        self._media_lookup = media_lookup
        self._profile_viewing_policy = profile_viewing_policy

    async def execute(self, input_dto: GetProgressInput) -> ProgressOutput | None:
        """Return the caller's progress for the media, or ``None`` if absent or hidden."""
        profile_id = ProfileId(input_dto.profile_id)
        media_id = WatchableMediaId(input_dto.media_id)
        async with self._uow_factory() as uow:
            progress = await uow.progress.find_by_media_id(media_id, profile_id)
        if progress is None:
            return None

        policy = await self._profile_viewing_policy.find_for_profile(profile_id)
        if not await is_title_visible(self._media_lookup, title_of(media_id), policy):
            return None
        return ProgressOutput.from_entity(progress)


__all__ = ["GetProgressUseCase"]
