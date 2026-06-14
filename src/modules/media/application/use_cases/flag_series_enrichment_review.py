"""Use case: admin flags a series' enrichment as wrong."""

from src.building_blocks.application.errors import ResourceNotFoundException
from src.modules.media.application.dtos.admin_relink_dtos import (
    FlagSeriesEnrichmentReviewInput,
    FlagSeriesEnrichmentReviewOutput,
)
from src.modules.media.application.unit_of_work import MediaUnitOfWorkFactory
from src.modules.media.domain.value_objects import SeriesId


class FlagSeriesEnrichmentReviewUseCase:
    """Put a wrongly-enriched series back on the review queue.

    Unlike the automatic failure flag (set by
    ``EnrichSeriesMetadataUseCase`` when no TMDB match is found), this
    is an operator-driven command for series that *did* enrich but
    matched the wrong title. Flagging surfaces the series on the admin
    ``needs-review`` listing, from where the operator relinks to the
    correct TMDB id. The flag is cleared on the next successful
    enrichment.

    Args:
        uow_factory: Factory that opens a fresh media Unit of Work.
    """

    def __init__(self, uow_factory: MediaUnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def execute(
        self,
        input_dto: FlagSeriesEnrichmentReviewInput,
    ) -> FlagSeriesEnrichmentReviewOutput:
        """Flag the series for enrichment review.

        Args:
            input_dto: Input carrying the series id to flag.

        Returns:
            The flag state after the command.

        Raises:
            ResourceNotFoundException: When no series matches the id.
        """
        async with self._uow_factory() as uow:
            series = await uow.series.find_by_id(SeriesId(input_dto.series_id))
            if not series:
                raise ResourceNotFoundException.for_resource("Series", input_dto.series_id)

            flagged = series.with_enrichment_review_flagged()
            # Idempotent: ``with_enrichment_review_flagged`` returns the
            # same instance when already flagged, so only persist on a
            # real state change.
            if flagged is not series:
                await uow.series.save(flagged)

        return FlagSeriesEnrichmentReviewOutput(
            series_id=input_dto.series_id,
            needs_enrichment_review=True,
        )


__all__ = ["FlagSeriesEnrichmentReviewUseCase"]
