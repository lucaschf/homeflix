"""SetCreditsMarkerUseCase — apply a MANUAL credits marker to a title."""

from src.building_blocks.application.errors import ResourceNotFoundException
from src.modules.media.application.dtos.credits_dtos import (
    CreditsMarkerOutput,
    SetCreditsMarkerInput,
)
from src.modules.media.application.unit_of_work import MediaUnitOfWorkFactory
from src.modules.media.application.use_cases._credits_media_helpers import (
    credits_marker_to_output,
    fetch_creditable,
    parse_creditable_id,
    update_creditable_credits,
)
from src.modules.media.domain.value_objects import (
    CreditsDetectionState,
    CreditsMarker,
    CreditsMarkerSource,
)


class SetCreditsMarkerUseCase:
    """Set or replace the credits marker on a movie or episode (manual edit).

    The marker is persisted as ``MANUAL`` and the title's detection state
    moves to ``COMPLETED`` — the auto-detection job recognises both and
    skips the title on subsequent ticks. The domain layer enforces
    ``start_seconds <= duration`` (via ``with_credits_marker``), raising a
    domain exception the global handler maps to HTTP 422.

    Example:
        >>> use_case = SetCreditsMarkerUseCase(uow_factory)
        >>> await use_case.execute(
        ...     SetCreditsMarkerInput(media_id="mov_abc123abc123", start_seconds=5400),
        ... )
    """

    def __init__(self, uow_factory: MediaUnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def execute(self, input_dto: SetCreditsMarkerInput) -> CreditsMarkerOutput:
        """Persist a manual credits marker on the movie/episode.

        Args:
            input_dto: Media id (mov_xxx / epi_xxx) and credits onset.

        Returns:
            ``CreditsMarkerOutput`` mirroring the persisted marker.

        Raises:
            ResourceNotFoundException: If the id is not a movie/episode or
                no such title exists.
            BusinessRuleViolationException: If ``start_seconds`` exceeds
                the title's duration.
        """
        media_id = parse_creditable_id(input_dto.media_id)
        marker = CreditsMarker(
            start_seconds=input_dto.start_seconds,
            source=CreditsMarkerSource.MANUAL,
        )

        async with self._uow_factory() as uow:
            entity = await fetch_creditable(uow, media_id)
            if entity is None:
                raise ResourceNotFoundException.for_resource("CreditableMedia", input_dto.media_id)

            # Enforce the duration-bound invariant on the entity; the
            # returned copy is discarded — persistence uses the direct
            # column update so the parent aggregate stays untouched.
            entity.with_credits_marker(marker)

            await update_creditable_credits(uow, media_id, marker, CreditsDetectionState.COMPLETED)

        return credits_marker_to_output(marker)


__all__ = ["SetCreditsMarkerUseCase"]
