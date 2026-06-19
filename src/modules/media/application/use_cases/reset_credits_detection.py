"""ResetCreditsDetectionUseCase — requeue one title for credits detection."""

from src.building_blocks.application.errors import ResourceNotFoundException
from src.modules.media.application.dtos.credits_dtos import (
    ResetCreditsDetectionInput,
    ResetCreditsDetectionOutput,
)
from src.modules.media.application.unit_of_work import MediaUnitOfWorkFactory
from src.modules.media.application.use_cases._credits_media_helpers import (
    fetch_creditable,
    parse_creditable_id,
    update_creditable_credits,
)
from src.modules.media.domain.value_objects import CreditsDetectionState


class ResetCreditsDetectionUseCase:
    """Return a movie/episode to the credits-detection queue.

    Sets the title's ``credits_detection_state`` back to ``NOT_STARTED``
    so the next job tick reprocesses it. An ``AUTO_DETECTED`` marker is
    cleared so the re-run starts clean; a ``MANUAL`` marker is preserved
    (the job skips manually-marked titles, mirroring intro reset).

    Useful for re-running detection on one title after re-tuning or
    widening the window — a ``COMPLETED`` title would otherwise never be
    picked up again.

    Example:
        >>> use_case = ResetCreditsDetectionUseCase(uow_factory)
        >>> await use_case.execute(
        ...     ResetCreditsDetectionInput(media_id="mov_abc123abc123"),
        ... )
    """

    def __init__(self, uow_factory: MediaUnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def execute(self, input_dto: ResetCreditsDetectionInput) -> ResetCreditsDetectionOutput:
        """Requeue the title for credits detection.

        Args:
            input_dto: External id of the movie/episode to requeue.

        Returns:
            Whether an auto-detected marker was cleared.

        Raises:
            ResourceNotFoundException: If the id is not a movie/episode or
                no such title exists.
        """
        media_id = parse_creditable_id(input_dto.media_id)
        async with self._uow_factory() as uow:
            entity = await fetch_creditable(uow, media_id)
            if entity is None:
                raise ResourceNotFoundException.for_resource("CreditableMedia", input_dto.media_id)

            existing = entity.credits
            keep_manual = existing is not None and existing.is_manual
            await update_creditable_credits(
                uow,
                media_id,
                existing if keep_manual else None,
                CreditsDetectionState.NOT_STARTED,
            )
            marker_cleared = existing is not None and not keep_manual

        return ResetCreditsDetectionOutput(marker_cleared=marker_cleared)


__all__ = ["ResetCreditsDetectionUseCase"]
