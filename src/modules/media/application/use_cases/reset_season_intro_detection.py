"""ResetSeasonIntroDetectionUseCase — requeue one season for intro detection."""

from src.building_blocks.application.errors import ResourceNotFoundException
from src.modules.media.application.dtos.intro_dtos import (
    ResetSeasonIntroDetectionInput,
    ResetSeasonIntroDetectionOutput,
)
from src.modules.media.application.unit_of_work import MediaUnitOfWorkFactory
from src.modules.media.domain.value_objects import IntroDetectionState, SeasonId


class ResetSeasonIntroDetectionUseCase:
    """Return a single season to the auto-detection queue.

    Sets the season's ``intro_detection_state`` back to ``NOT_STARTED``
    (so the next job tick reprocesses it) and clears its AUTO_DETECTED
    episode markers so the re-run starts clean. MANUAL markers are
    preserved — the job skips those episodes anyway, and they represent
    deliberate operator edits.

    Useful for re-running detection on one season after switching
    algorithm, widening the analysis window, or re-tuning — a season
    already ``COMPLETED`` would otherwise never be picked up again.

    Example:
        >>> use_case = ResetSeasonIntroDetectionUseCase(uow_factory)
        >>> await use_case.execute(
        ...     ResetSeasonIntroDetectionInput(season_id="ssn_abc123abc123"),
        ... )
    """

    def __init__(self, uow_factory: MediaUnitOfWorkFactory) -> None:
        """Initialize the use case.

        Args:
            uow_factory: Factory that opens a fresh media Unit of Work.
        """
        self._uow_factory = uow_factory

    async def execute(
        self,
        input_dto: ResetSeasonIntroDetectionInput,
    ) -> ResetSeasonIntroDetectionOutput:
        """Reset intro detection for the season.

        Args:
            input_dto: External id of the season to requeue.

        Returns:
            Count of auto-detected markers cleared.

        Raises:
            ResourceNotFoundException: If no season with the id exists.
        """
        season_id = SeasonId(input_dto.season_id)

        async with self._uow_factory() as uow:
            requeued = await uow.series.update_season_intro_detection(
                season_id,
                IntroDetectionState.NOT_STARTED,
                attempted_at=None,
                error=None,
            )
            if not requeued:
                raise ResourceNotFoundException.for_resource("Season", input_dto.season_id)

            markers_cleared = await uow.series.clear_auto_intro_markers_for_season(season_id)

        return ResetSeasonIntroDetectionOutput(markers_cleared=markers_cleared)


__all__ = ["ResetSeasonIntroDetectionUseCase"]
