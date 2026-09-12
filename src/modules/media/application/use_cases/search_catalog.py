"""SearchCatalogUseCase - full-text search across movies and series."""

import asyncio

from src.modules.media.application.dtos.search_dtos import (
    SearchInput,
    SearchItemOutput,
    SearchOutput,
)
from src.modules.media.application.ports.profile_viewing_policy_port import (
    ProfileViewingPolicyPort,
)
from src.modules.media.application.unit_of_work import MediaUnitOfWorkFactory
from src.modules.media.domain.entities import Movie, Series
from src.shared_kernel.content_policy import ViewingPolicy
from src.shared_kernel.value_objects import MediaType
from src.shared_kernel.value_objects.profile_id import ProfileId


class SearchCatalogUseCase:
    """Cross-cutting full-text search over both media types.

    Queries both repositories in parallel via ``asyncio.gather``,
    pools the results, sorts by FTS relevance rank, and trims to
    the requested limit. When ``media_type`` is set, only the
    matching repository is queried — the other is skipped entirely,
    same pattern as ``ListByGenreUseCase``.

    The FTS5 ``bm25()`` rank is a negative float where more-negative
    means more relevant. Sorting ascending puts the best matches
    first. Ranks from movies and series are directly compared —
    bm25 is query-relative, so the same query against different
    tables produces comparable scores for practical purposes.
    """

    def __init__(
        self,
        uow_factory: MediaUnitOfWorkFactory,
        profile_viewing_policy: ProfileViewingPolicyPort,
    ) -> None:
        self._uow_factory = uow_factory
        self._profile_viewing_policy = profile_viewing_policy

    async def execute(self, input_dto: SearchInput) -> SearchOutput:
        """Execute the search.

        Args:
            input_dto: ``profile_id``, search query, optional filters,
                lang, limit.

        Returns:
            ``SearchOutput`` with items sorted by relevance and a
            total count. A deny-all profile yields an empty result
            without opening a UoW.
        """
        policy = await self._profile_viewing_policy.find_for_profile(
            ProfileId(input_dto.profile_id)
        )
        if policy.denies_everything:
            return SearchOutput(items=[], total=0)

        # Fetch from both repos in parallel, skipping the excluded
        # type when a filter is active. Each branch opens its own
        # UoW so parallel queries run on independent sessions
        # (AsyncSession forbids concurrent execution on the same one).
        movie_hits: list[tuple[Movie, float]] = []
        series_hits: list[tuple[Series, float]] = []

        if input_dto.media_type is MediaType.MOVIE:
            movie_hits = await self._search_movies(input_dto, policy)
        elif input_dto.media_type is MediaType.SERIES:
            series_hits = await self._search_series(input_dto, policy)
        else:
            movie_hits, series_hits = await asyncio.gather(
                self._search_movies(input_dto, policy),
                self._search_series(input_dto, policy),
            )

        # Pool and sort by rank (ascending = most relevant first)
        combined: list[tuple[Movie | Series, float, str]] = [
            (entity, rank, "movie") for entity, rank in movie_hits
        ] + [(entity, rank, "series") for entity, rank in series_hits]
        combined.sort(key=lambda item: item[1])

        # Trim to limit and map to output
        page = combined[: input_dto.limit]
        items = [self._to_output(kind, entity, input_dto.lang) for entity, _, kind in page]

        return SearchOutput(items=items, total=len(combined))

    async def _search_movies(
        self, input_dto: SearchInput, policy: ViewingPolicy
    ) -> list[tuple[Movie, float]]:
        async with self._uow_factory() as uow:
            return await uow.movies.search(
                input_dto.query,
                genre=input_dto.genre,
                year_min=input_dto.year_min,
                year_max=input_dto.year_max,
                limit=input_dto.limit,
                policy=policy,
            )

    async def _search_series(
        self, input_dto: SearchInput, policy: ViewingPolicy
    ) -> list[tuple[Series, float]]:
        async with self._uow_factory() as uow:
            return await uow.series.search(
                input_dto.query,
                genre=input_dto.genre,
                year_min=input_dto.year_min,
                year_max=input_dto.year_max,
                limit=input_dto.limit,
                policy=policy,
            )

    @staticmethod
    def _to_output(kind: str, entity: Movie | Series, lang: str) -> SearchItemOutput:
        """Map a domain entity to the search result DTO."""
        if isinstance(entity, Movie):
            return SearchItemOutput(
                id=str(entity.id),
                type=kind,
                title=entity.get_title(lang),
                year=entity.year.value,
                synopsis=entity.get_synopsis(lang),
                poster_path=entity.get_poster_path(lang),
                backdrop_path=entity.get_backdrop_path(lang),
                genres=entity.get_genres(lang),
            )
        # Series
        return SearchItemOutput(
            id=str(entity.id),
            type=kind,
            title=entity.get_title(lang),
            year=entity.start_year.value,
            synopsis=entity.get_synopsis(lang),
            poster_path=entity.get_poster_path(lang),
            backdrop_path=entity.get_backdrop_path(lang),
            genres=entity.get_genres(lang),
        )


__all__ = ["SearchCatalogUseCase"]
