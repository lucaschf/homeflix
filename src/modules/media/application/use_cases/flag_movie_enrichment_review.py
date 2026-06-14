"""Use case: admin flags a movie's enrichment as wrong."""

from src.building_blocks.application.errors import ResourceNotFoundException
from src.modules.media.application.dtos.admin_relink_dtos import (
    FlagMovieEnrichmentReviewInput,
    FlagMovieEnrichmentReviewOutput,
)
from src.modules.media.application.unit_of_work import MediaUnitOfWorkFactory
from src.modules.media.domain.value_objects import MovieId


class FlagMovieEnrichmentReviewUseCase:
    """Put a wrongly-enriched movie back on the review queue.

    Unlike the automatic failure flag (set by
    ``EnrichMovieMetadataUseCase`` when no TMDB match is found), this
    is an operator-driven command for movies that *did* enrich but
    matched the wrong title. Flagging surfaces the movie on the admin
    ``needs-review`` listing, from where the operator picks the correct
    TMDB id via the suggestions picker and relinks. The flag is cleared
    on the next successful enrichment.

    Args:
        uow_factory: Factory that opens a fresh media Unit of Work.
    """

    def __init__(self, uow_factory: MediaUnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def execute(
        self,
        input_dto: FlagMovieEnrichmentReviewInput,
    ) -> FlagMovieEnrichmentReviewOutput:
        """Flag the movie for enrichment review.

        Args:
            input_dto: Input carrying the movie id to flag.

        Returns:
            The flag state after the command.

        Raises:
            ResourceNotFoundException: When no movie matches the id.
        """
        async with self._uow_factory() as uow:
            movie = await uow.movies.find_by_id(MovieId(input_dto.movie_id))
            if not movie:
                raise ResourceNotFoundException.for_resource("Movie", input_dto.movie_id)

            flagged = movie.with_enrichment_review_flagged()
            # Idempotent: ``with_enrichment_review_flagged`` returns the
            # same instance when already flagged, so only persist on a
            # real state change.
            if flagged is not movie:
                await uow.movies.save(flagged)

        return FlagMovieEnrichmentReviewOutput(
            movie_id=input_dto.movie_id,
            needs_enrichment_review=True,
        )


__all__ = ["FlagMovieEnrichmentReviewUseCase"]
