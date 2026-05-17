"""Use case: admin re-points a movie at a specific TMDB id."""

from src.building_blocks.application.errors import (
    ResourceNotFoundException,
    UseCaseValidationException,
)
from src.modules.media.application.dtos.admin_relink_dtos import (
    RelinkMovieInput,
    RelinkMovieOutput,
)
from src.modules.media.application.dtos.enrichment_dtos import EnrichMediaInput
from src.modules.media.application.unit_of_work import MediaUnitOfWorkFactory
from src.modules.media.application.use_cases.enrich_movie_metadata import (
    EnrichMovieMetadataUseCase,
)
from src.modules.media.domain.value_objects import MovieId, TmdbId


class RelinkMovieUseCase:
    """Apply an admin-picked TMDB id to a movie and re-enrich.

    Flow:
        1. Validate ``media_type``. ``"tv"`` is rejected with a
           ``UseCaseValidationException`` — the Movie→Series
           conversion lives in a follow-up PR (the deferred
           "Option C" promote-to-series flow).
        2. Load the movie and stamp the picked ``tmdb_id``.
        3. Force-enrich. ``EnrichMovieMetadataUseCase`` resolves
           ``get_movie_by_id`` first when ``movie.tmdb_id`` is set,
           so the admin's pick wins over the title-based search.
        4. Surface the enrichment outcome to the caller.

    Args:
        uow_factory: Factory that opens a fresh media Unit of Work.
        enrich_use_case: ``EnrichMovieMetadataUseCase`` instance used
            to refresh the entity after the new id is stamped.
    """

    def __init__(
        self,
        uow_factory: MediaUnitOfWorkFactory,
        enrich_use_case: EnrichMovieMetadataUseCase,
    ) -> None:
        self._uow_factory = uow_factory
        self._enrich = enrich_use_case

    async def execute(self, input_dto: RelinkMovieInput) -> RelinkMovieOutput:
        """Execute the relink command."""
        if input_dto.media_type == "tv":
            raise UseCaseValidationException(
                message=(
                    "Cross-type relink (movie → series) is not yet "
                    "supported. The TMDB candidate you picked is a TV "
                    "series; a dedicated promote-to-series endpoint "
                    "will handle that conversion in a follow-up."
                ),
                message_code="RELINK_CROSS_TYPE_NOT_SUPPORTED",
            )

        async with self._uow_factory() as uow:
            movie = await uow.movies.find_by_id(MovieId(input_dto.movie_id))
            if not movie:
                raise ResourceNotFoundException.for_resource("Movie", input_dto.movie_id)
            # Stamp the picked id so the enrichment path resolves
            # via ``get_movie_by_id`` instead of the title search.
            # The flag is cleared by the enrich use case on success.
            movie = movie.with_updates(tmdb_id=TmdbId(input_dto.tmdb_id))
            await uow.movies.save(movie)

        result = await self._enrich.execute(
            EnrichMediaInput(media_id=input_dto.movie_id, force=True),
        )
        return RelinkMovieOutput(
            movie_id=result.media_id,
            enriched=result.enriched,
            provider=result.provider,
            error=result.error,
        )


__all__ = ["RelinkMovieUseCase"]
