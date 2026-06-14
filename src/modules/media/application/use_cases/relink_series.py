"""Use case: admin re-points a series at a specific TMDB id."""

from src.building_blocks.application.errors import (
    ResourceNotFoundException,
    UseCaseValidationException,
)
from src.modules.media.application.dtos.admin_relink_dtos import (
    RelinkSeriesInput,
    RelinkSeriesOutput,
)
from src.modules.media.application.dtos.enrichment_dtos import EnrichMediaInput
from src.modules.media.application.unit_of_work import MediaUnitOfWorkFactory
from src.modules.media.application.use_cases.enrich_series_metadata import (
    EnrichSeriesMetadataUseCase,
)
from src.modules.media.domain.value_objects import SeriesId, TmdbId


class RelinkSeriesUseCase:
    """Apply an admin-picked TMDB id to a series and re-enrich.

    Flow:
        1. Validate ``media_type``. ``"movie"`` is rejected with a
           ``UseCaseValidationException`` — converting a series back
           into a movie is not supported.
        2. Load the series and stamp the picked ``tmdb_id``.
        3. Force-enrich. ``EnrichSeriesMetadataUseCase`` resolves
           ``get_series_by_id`` first when ``series.tmdb_id`` is set,
           so the admin's pick wins over the title-based search, and
           clears the review flag on success.
        4. Surface the enrichment outcome to the caller.

    Args:
        uow_factory: Factory that opens a fresh media Unit of Work.
        enrich_use_case: ``EnrichSeriesMetadataUseCase`` instance used
            to refresh the entity after the new id is stamped.
    """

    def __init__(
        self,
        uow_factory: MediaUnitOfWorkFactory,
        enrich_use_case: EnrichSeriesMetadataUseCase,
    ) -> None:
        self._uow_factory = uow_factory
        self._enrich = enrich_use_case

    async def execute(self, input_dto: RelinkSeriesInput) -> RelinkSeriesOutput:
        """Execute the relink command."""
        if input_dto.media_type == "movie":
            raise UseCaseValidationException(
                message=(
                    "Cross-type relink (series → movie) is not "
                    "supported. Pick a TV candidate from the series "
                    "suggestion picker."
                ),
                message_code="RELINK_CROSS_TYPE_NOT_SUPPORTED",
            )

        async with self._uow_factory() as uow:
            series = await uow.series.find_by_id(SeriesId(input_dto.series_id))
            if not series:
                raise ResourceNotFoundException.for_resource("Series", input_dto.series_id)
            # Stamp the picked id so the enrichment path resolves
            # via ``get_series_by_id`` instead of the title search.
            # The flag is cleared by the enrich use case on success.
            series = series.with_updates(tmdb_id=TmdbId(input_dto.tmdb_id))
            await uow.series.save(series)

        result = await self._enrich.execute(
            EnrichMediaInput(media_id=input_dto.series_id, force=True),
        )
        return RelinkSeriesOutput(
            series_id=result.media_id,
            enriched=result.enriched,
            provider=result.provider,
            error=result.error,
        )


__all__ = ["RelinkSeriesUseCase"]
