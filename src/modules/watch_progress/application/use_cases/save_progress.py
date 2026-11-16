"""SaveProgressUseCase - Save or update watch progress."""

from collections.abc import Sequence

from src.building_blocks.application.event_bus import EventBus
from src.building_blocks.domain.events import DomainEvent
from src.modules.watch_progress.application.dtos import ProgressOutput, SaveProgressInput
from src.modules.watch_progress.application.ports import (
    MediaLookupPort,
    ProfileViewingPolicyPort,
)
from src.modules.watch_progress.application.unit_of_work import (
    WatchProgressUnitOfWorkFactory,
)
from src.modules.watch_progress.application.use_cases._title_gate import (
    is_title_visible,
    title_not_found,
    title_of,
)
from src.modules.watch_progress.domain.entities import WatchProgress
from src.modules.watch_progress.domain.events import WatchCompletedEvent
from src.modules.watch_progress.domain.value_objects import (
    SubtitlePreference,
    WatchableMediaId,
    WatchableMediaType,
)
from src.shared_kernel.integration_events import MovieCompletedEvent
from src.shared_kernel.value_objects.media_id import MovieId
from src.shared_kernel.value_objects.profile_id import ProfileId


class SaveProgressUseCase:
    """Save or update watch progress for a media item, scoped to one profile.

    Progress is only recorded on a title the profile can see. The check
    runs before the progress transaction opens and applies whether or not
    a row already exists, so the answer never depends on past progress.

    When the save finishes a movie, ``MovieCompletedEvent`` is published
    after the progress transaction commits, so ``collections`` can take
    the movie off the profile's watchlist.
    """

    def __init__(
        self,
        uow_factory: WatchProgressUnitOfWorkFactory,
        media_lookup: MediaLookupPort,
        profile_viewing_policy: ProfileViewingPolicyPort,
        event_bus: EventBus,
    ) -> None:
        """Initialize the use case.

        Args:
            uow_factory: Factory that opens a fresh watch progress UoW.
            media_lookup: Port for asking the catalog which titles are visible.
            profile_viewing_policy: Port resolving the caller's viewing policy.
            event_bus: Bus that publishes ``MovieCompletedEvent`` to other
                bounded contexts.
        """
        self._uow_factory = uow_factory
        self._media_lookup = media_lookup
        self._profile_viewing_policy = profile_viewing_policy
        self._event_bus = event_bus

    async def execute(self, input_dto: SaveProgressInput) -> ProgressOutput:
        """Persist progress for the caller's profile.

        Raises:
            ResourceNotFoundException: If the movie, or the episode's
                series, does not exist or the profile cannot see it —
                the two cases raise the same error.
        """
        profile_id = ProfileId(input_dto.profile_id)
        media_id = WatchableMediaId(input_dto.media_id)
        subtitle_track = SubtitlePreference.from_wire(input_dto.subtitle_track)

        title = title_of(media_id)
        policy = await self._profile_viewing_policy.find_for_profile(profile_id)
        if not await is_title_visible(self._media_lookup, title, policy):
            raise title_not_found(title)

        async with self._uow_factory() as uow:
            existing = await uow.progress.find_by_media_id(media_id, profile_id)

            if existing:
                progress = existing.update_position(
                    position_seconds=input_dto.position_seconds,
                    duration_seconds=input_dto.duration_seconds,
                    audio_track=input_dto.audio_track,
                    subtitle_track=subtitle_track,
                )
            else:
                progress = WatchProgress.create(
                    profile_id=profile_id,
                    media_id=media_id,
                    media_type=WatchableMediaType(input_dto.media_type),
                    position_seconds=input_dto.position_seconds,
                    duration_seconds=input_dto.duration_seconds,
                    audio_track=input_dto.audio_track,
                    subtitle_track=subtitle_track,
                )

            events = progress.pull_events()
            saved = await uow.progress.save(progress)

        # After the commit, so a handler never acts on progress that rolled back.
        for event in _completed_movies(events):
            await self._event_bus.publish(event)
        return ProgressOutput.from_entity(saved)


def _completed_movies(events: Sequence[DomainEvent]) -> list[MovieCompletedEvent]:
    """Translate finished movies into the published contract; episodes stay internal."""
    return [
        MovieCompletedEvent(profile_id=event.profile_id, movie_id=MovieId(event.media_id.value))
        for event in events
        if isinstance(event, WatchCompletedEvent) and event.media_id.is_movie
    ]


__all__ = ["SaveProgressUseCase"]
