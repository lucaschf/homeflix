"""ResetSeasonIntroDetectionUseCase — requeue one season for intro detection."""

from src.building_blocks.application.errors import ResourceNotFoundException
from src.modules.media.application.dtos.intro_dtos import (
    ResetSeasonIntroDetectionInput,
    ResetSeasonIntroDetectionOutput,
)
from src.modules.media.application.ports import IntroDetectionRunnerPort
from src.modules.media.application.unit_of_work import MediaUnitOfWorkFactory
from src.modules.media.domain.value_objects import IntroDetectionState, SeasonId


class ResetSeasonIntroDetectionUseCase:
    """Return a single season to the auto-detection queue.

    Sets the season's ``intro_detection_state`` back to ``NOT_STARTED``
    (so the next job tick reprocesses it) and clears its AUTO_DETECTED
    episode markers so the re-run starts clean. MANUAL markers are
    preserved — the job skips those episodes anyway, and they represent
    deliberate operator edits.

    With ``run_now`` the season does not wait for the next tick: a run
    is launched for it in the background right after the reset commits.
    Detection is minutes-long, so the launch is fire-and-forget — the
    outcome shows up in the season's state and in the run history, not
    in this use case's output.

    Useful for re-running detection on one season after switching
    algorithm, widening the analysis window, or re-tuning — a season
    already ``COMPLETED`` would otherwise never be picked up again.

    Example:
        >>> use_case = ResetSeasonIntroDetectionUseCase(uow_factory, runner)
        >>> await use_case.execute(
        ...     ResetSeasonIntroDetectionInput(
        ...         season_id="ssn_abc123abc123",
        ...         run_now=True,
        ...     ),
        ... )
    """

    def __init__(
        self,
        uow_factory: MediaUnitOfWorkFactory,
        detection_runner: IntroDetectionRunnerPort,
    ) -> None:
        """Initialize the use case.

        Args:
            uow_factory: Factory that opens a fresh media Unit of Work.
            detection_runner: Launches an immediate detection run for a
                season, used when ``run_now`` is requested.
        """
        self._uow_factory = uow_factory
        self._detection_runner = detection_runner

    async def execute(
        self,
        input_dto: ResetSeasonIntroDetectionInput,
    ) -> ResetSeasonIntroDetectionOutput:
        """Reset intro detection for the season, optionally running it now.

        Args:
            input_dto: External id of the season to requeue, and whether
                to start detection immediately.

        Returns:
            Count of auto-detected markers cleared, plus whether an
            immediate run was started.

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

        # Launched only once the reset has committed, so the background
        # run observes the cleared markers rather than racing them.
        detection_started = (
            self._detection_runner.start_for_season(season_id) if input_dto.run_now else False
        )

        return ResetSeasonIntroDetectionOutput(
            markers_cleared=markers_cleared,
            detection_started=detection_started,
        )


__all__ = ["ResetSeasonIntroDetectionUseCase"]
