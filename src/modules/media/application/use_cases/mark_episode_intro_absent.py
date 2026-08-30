"""MarkEpisodeIntroAbsentUseCase — record that an episode has no intro."""

from src.building_blocks.application.errors import ResourceNotFoundException
from src.building_blocks.application.event_bus import EventBus
from src.building_blocks.domain import utc_now
from src.modules.media.application.dtos.intro_dtos import MarkEpisodeIntroAbsentInput
from src.modules.media.application.unit_of_work import MediaUnitOfWorkFactory
from src.modules.media.domain.events import IntroMarkedAbsentEvent
from src.modules.media.domain.value_objects import EpisodeId


class MarkEpisodeIntroAbsentUseCase:
    """Confirm that an episode has no opening sequence to skip.

    Some episodes genuinely have no intro — cold-open specials, clip
    shows, finales. Without a way to say so they sit as "pending"
    forever, holding their series below full coverage and getting
    re-analysed on every detection pass. This records the verdict:
    the episode counts as resolved and auto-detection skips it.

    Any existing marker is dropped, since the two states are mutually
    exclusive. Idempotent — re-marking an already-absent episode
    succeeds without dispatching a second event. To undo, clear the
    episode's intro, which returns it to the detection queue.

    Example:
        >>> use_case = MarkEpisodeIntroAbsentUseCase(uow_factory, event_bus)
        >>> await use_case.execute(MarkEpisodeIntroAbsentInput(
        ...     episode_id="epi_abc123abc123",
        ... ))
    """

    def __init__(
        self,
        uow_factory: MediaUnitOfWorkFactory,
        event_bus: EventBus | None = None,
    ) -> None:
        """Initialize the use case.

        Args:
            uow_factory: Factory that opens a fresh media Unit of Work.
            event_bus: Optional event bus for publishing
                ``IntroMarkedAbsentEvent``. Dispatched only when the
                episode was not already flagged.
        """
        self._uow_factory = uow_factory
        self._event_bus = event_bus

    async def execute(self, input_dto: MarkEpisodeIntroAbsentInput) -> None:
        """Flag the episode as having no intro.

        Args:
            input_dto: Episode id.

        Raises:
            ResourceNotFoundException: If no episode with the given id exists.
        """
        episode_id = EpisodeId(input_dto.episode_id)

        async with self._uow_factory() as uow:
            episode = await uow.series.find_episode_by_id(episode_id)
            if episode is None:
                raise ResourceNotFoundException.for_resource("Episode", input_dto.episode_id)

            already_absent = episode.intro_absent_at is not None
            if not already_absent:
                await uow.series.mark_episode_intro_absent(episode_id, utc_now())

            series_id = episode.series_id

        if not already_absent and self._event_bus is not None:
            await self._event_bus.publish(
                IntroMarkedAbsentEvent(
                    episode_id=episode_id,
                    series_id=series_id,
                )
            )


__all__ = ["MarkEpisodeIntroAbsentUseCase"]
