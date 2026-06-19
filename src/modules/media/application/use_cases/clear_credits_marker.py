"""ClearCreditsMarkerUseCase — remove a title's credits marker."""

from src.building_blocks.application.errors import ResourceNotFoundException
from src.modules.media.application.unit_of_work import MediaUnitOfWorkFactory
from src.modules.media.application.use_cases._credits_media_helpers import (
    fetch_creditable,
    parse_creditable_id,
    update_creditable_credits,
)
from src.modules.media.domain.value_objects import CreditsDetectionState


class ClearCreditsMarkerUseCase:
    """Remove the credits marker from a movie or episode.

    Clears the marker columns and sets the detection state to
    ``COMPLETED`` (not ``NOT_STARTED``) so the auto-detection job does
    not immediately re-add a marker — clearing is a deliberate "this
    title has no skippable credits" statement. To instead re-run
    detection, use :class:`ResetCreditsDetectionUseCase`.

    Example:
        >>> use_case = ClearCreditsMarkerUseCase(uow_factory)
        >>> await use_case.execute("epi_abc123abc123")
    """

    def __init__(self, uow_factory: MediaUnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def execute(self, media_id: str) -> None:
        """Clear the credits marker on the movie/episode.

        Args:
            media_id: External id of the movie (mov_xxx) or episode
                (epi_xxx).

        Raises:
            ResourceNotFoundException: If the id is not a movie/episode or
                no such title exists.
        """
        parsed = parse_creditable_id(media_id)
        async with self._uow_factory() as uow:
            entity = await fetch_creditable(uow, parsed)
            if entity is None:
                raise ResourceNotFoundException.for_resource("CreditableMedia", media_id)
            await update_creditable_credits(uow, parsed, None, CreditsDetectionState.COMPLETED)


__all__ = ["ClearCreditsMarkerUseCase"]
