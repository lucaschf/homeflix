"""GetRelatedMoviesUseCase — TMDB recommendations filtered by library."""

from dataclasses import dataclass

from src.modules.media.application.dtos.movie_dtos import MovieSummaryOutput
from src.modules.media.application.ports import MetadataProvider
from src.modules.media.application.unit_of_work import MediaUnitOfWorkFactory
from src.modules.media.application.use_cases._movie_summary_helpers import to_movie_summary
from src.modules.media.domain.value_objects import MovieId


@dataclass(frozen=True)
class GetRelatedMoviesInput:
    """Input for ``GetRelatedMoviesUseCase``.

    Attributes:
        movie_id: External id of the movie to look up recommendations for.
        lang: Language for localized fields on the response.
        limit: Maximum number of related movies to return.
    """

    movie_id: str
    lang: str = "en"
    limit: int = 12


class GetRelatedMoviesUseCase:
    """Return movies in the library that TMDB recommends for the input.

    Pulls TMDB's recommendation list for the input movie (falling back
    to TMDB's "similar" endpoint when recommendations is empty), then
    intersects with the local catalog by ``tmdb_id``. The TMDB ordering
    (by relevance) is preserved on the way out.

    The feature is best-effort polish: any failure (movie not found,
    movie not enriched with TMDB id, provider unavailable, no overlap
    with local catalog) yields an empty list rather than raising — the
    UI simply doesn't render the carousel.

    Example:
        >>> use_case = GetRelatedMoviesUseCase(uow_factory, tmdb_client)
        >>> result = await use_case.execute(GetRelatedMoviesInput("mov_abc"))
        >>> [m.title for m in result]
        ['Interstellar', 'The Prestige', ...]
    """

    def __init__(
        self,
        uow_factory: MediaUnitOfWorkFactory,
        metadata_provider: MetadataProvider,
    ) -> None:
        self._uow_factory = uow_factory
        self._metadata = metadata_provider

    async def execute(self, input_dto: GetRelatedMoviesInput) -> list[MovieSummaryOutput]:
        """Run the lookup."""
        async with self._uow_factory() as uow:
            source = await uow.movies.find_by_id(MovieId(input_dto.movie_id))
            if source is None or source.tmdb_id is None:
                return []

            tmdb_ids = await self._metadata.get_movie_recommendations(source.tmdb_id.value)
            if not tmdb_ids:
                return []

            # Trim before hitting the DB so a TMDB result of 50 doesn't
            # cost us 50 rows when the carousel only shows ``limit``.
            # Slight over-fetch (2x) so a few catalog gaps don't leave
            # the carousel sparse.
            candidate_ids = tmdb_ids[: input_dto.limit * 2]
            local = await uow.movies.find_by_tmdb_ids(candidate_ids)

        # Preserve TMDB's relevance ordering by iterating the request
        # list rather than the dict's insertion order.
        ordered: list[MovieSummaryOutput] = []
        for tid in candidate_ids:
            movie = local.get(tid)
            if movie is None:
                continue
            ordered.append(to_movie_summary(movie, input_dto.lang))
            if len(ordered) >= input_dto.limit:
                break
        return ordered


__all__ = ["GetRelatedMoviesInput", "GetRelatedMoviesUseCase"]
