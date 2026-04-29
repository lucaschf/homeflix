"""SetEpisodeIntroUseCase — apply a MANUAL intro marker to an episode."""

from src.building_blocks.application.errors import ResourceNotFoundException
from src.building_blocks.application.event_bus import EventBus
from src.modules.media.application.dtos.intro_dtos import (
    IntroMarkerOutput,
    SetEpisodeIntroInput,
)
from src.modules.media.application.unit_of_work import MediaUnitOfWorkFactory
from src.modules.media.application.use_cases._intro_marker_helpers import (
    intro_marker_to_output,
)
from src.modules.media.domain.events import IntroManuallySetEvent
from src.modules.media.domain.value_objects import (
    EpisodeId,
    IntroMarker,
    IntroMarkerSource,
)


class SetEpisodeIntroUseCase:
    """Set or replace the intro marker on an episode (manual edit).

    The marker is always persisted as ``MANUAL`` — the auto-detection
    job recognises this and skips the episode on subsequent runs. The
    domain layer enforces ``end > start`` (via the VO) and
    ``end <= duration`` (via ``Episode.with_intro_marker``); both raise
    domain exceptions that the global handler maps to HTTP 422.

    Example:
        >>> use_case = SetEpisodeIntroUseCase(uow_factory, event_bus)
        >>> result = await use_case.execute(SetEpisodeIntroInput(
        ...     episode_id="epi_abc123abc123",
        ...     start_seconds=12,
        ...     end_seconds=98,
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
                ``IntroManuallySetEvent``. When omitted, events are
                silently dropped (mirrors the scan use-case convention).
        """
        self._uow_factory = uow_factory
        self._event_bus = event_bus

    async def execute(self, input_dto: SetEpisodeIntroInput) -> IntroMarkerOutput:
        """Persist the intro marker and emit a ``IntroManuallySetEvent``.

        Args:
            input_dto: Episode id and intro range.

        Returns:
            ``IntroMarkerOutput`` mirroring the persisted state.

        Raises:
            ResourceNotFoundException: If no episode with the given id exists.
            DomainValidationException: If ``start``/``end`` are invalid
                (negative, end <= start).
            BusinessRuleViolationException: If
                ``end_seconds > episode.duration``.
        """
        episode_id = EpisodeId(input_dto.episode_id)
        marker = IntroMarker(
            start_seconds=input_dto.start_seconds,
            end_seconds=input_dto.end_seconds,
            source=IntroMarkerSource.MANUAL,
        )

        async with self._uow_factory() as uow:
            episode = await uow.series.find_episode_by_id(episode_id)
            if episode is None:
                raise ResourceNotFoundException.for_resource("Episode", input_dto.episode_id)

            # Trigger the duration-bound check on the entity. The
            # returned instance is discarded — persistence goes through
            # the direct-update path so the parent Series aggregate
            # stays untouched.
            episode.with_intro_marker(marker)

            await uow.series.update_episode_intro(episode_id, marker)
            series_id = str(episode.series_id)

        if self._event_bus is not None:
            await self._event_bus.publish(
                IntroManuallySetEvent(
                    episode_id=str(episode_id),
                    series_id=series_id,
                    start_seconds=marker.start_seconds,
                    end_seconds=marker.end_seconds,
                )
            )

        return intro_marker_to_output(marker)


__all__ = ["SetEpisodeIntroUseCase"]
