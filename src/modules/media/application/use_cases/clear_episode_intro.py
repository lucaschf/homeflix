"""ClearEpisodeIntroUseCase — remove the intro marker from an episode."""

from src.building_blocks.application.errors import ResourceNotFoundException
from src.building_blocks.application.event_bus import EventBus
from src.modules.media.application.dtos.intro_dtos import ClearEpisodeIntroInput
from src.modules.media.application.unit_of_work import MediaUnitOfWorkFactory
from src.modules.media.domain.events import IntroClearedEvent
from src.modules.media.domain.value_objects import EpisodeId


class ClearEpisodeIntroUseCase:
    """Remove the intro marker from an episode.

    Idempotent: clearing an already-pending episode still succeeds (no
    event is dispatched). Clearing a previously-MANUAL marker — or a
    "no intro" verdict — returns the episode to the auto-detection
    queue on the next job tick; that is the operator's escape hatch
    when manual timestamps drift or a verdict was wrong.

    Example:
        >>> use_case = ClearEpisodeIntroUseCase(uow_factory, event_bus)
        >>> await use_case.execute(ClearEpisodeIntroInput(
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
                ``IntroClearedEvent``. Events are dispatched only when a
                marker was actually present.
        """
        self._uow_factory = uow_factory
        self._event_bus = event_bus

    async def execute(self, input_dto: ClearEpisodeIntroInput) -> None:
        """Clear the intro marker if present.

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

            # Also reopens a "no intro" verdict: clearing is the single
            # undo for either decision, so the episode returns to
            # pending and rejoins the detection queue.
            had_state = episode.intro is not None or episode.intro_absent_at is not None
            if had_state:
                await uow.series.update_episode_intro(episode_id, None)

            series_id = episode.series_id

        if had_state and self._event_bus is not None:
            await self._event_bus.publish(
                IntroClearedEvent(
                    episode_id=episode_id,
                    series_id=series_id,
                )
            )


__all__ = ["ClearEpisodeIntroUseCase"]
