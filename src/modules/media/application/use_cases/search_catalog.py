"""SearchCatalogUseCase - full-text search across movies and series."""

import asyncio
from collections.abc import Sequence

from src.modules.media.application.dtos.search_dtos import (
    SearchInput,
    SearchItemOutput,
    SearchOutput,
)
from src.modules.media.application.ports.profile_library_access_port import (
    ProfileLibraryAccessPort,
)
from src.modules.media.application.unit_of_work import MediaUnitOfWorkFactory
from src.modules.media.domain.entities import Movie, Series


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
        profile_library_access: ProfileLibraryAccessPort,
    ) -> None:
        self._uow_factory = uow_factory
        self._profile_library_access = profile_library_access

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
        allowed = await self._profile_library_access.find_for_profile(input_dto.profile_id)
        if not allowed:
            return SearchOutput(items=[], total=0)

        # Fetch from both repos in parallel, skipping the excluded
        # type when a filter is active. Each branch opens its own
        # UoW so parallel queries run on independent sessions
        # (AsyncSession forbids concurrent execution on the same one).
        movie_hits: list[tuple[Movie, float]] = []
        series_hits: list[tuple[Series, float]] = []

        if input_dto.media_type == "movie":
            movie_hits = await self._search_movies(input_dto, allowed)
        elif input_dto.media_type == "series":
            series_hits = await self._search_series(input_dto, allowed)
        else:
            movie_hits, series_hits = await asyncio.gather(
                self._search_movies(input_dto, allowed),
                self._search_series(input_dto, allowed),
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
        self, input_dto: SearchInput, allowed_library_ids: Sequence[str]
    ) -> list[tuple[Movie, float]]:
        async with self._uow_factory() as uow:
            return await uow.movies.search(
                input_dto.query,
                genre=input_dto.genre,
                year_min=input_dto.year_min,
                year_max=input_dto.year_max,
                limit=input_dto.limit,
                allowed_library_ids=allowed_library_ids,
            )

    async def _search_series(
        self, input_dto: SearchInput, allowed_library_ids: Sequence[str]
    ) -> list[tuple[Series, float]]:
        async with self._uow_factory() as uow:
            return await uow.series.search(
                input_dto.query,
                genre=input_dto.genre,
                year_min=input_dto.year_min,
                year_max=input_dto.year_max,
                limit=input_dto.limit,
                allowed_library_ids=allowed_library_ids,
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
                poster_path=entity.poster_path.value if entity.poster_path else None,
                backdrop_path=entity.backdrop_path.value if entity.backdrop_path else None,
                genres=entity.get_genres(lang),
            )
        # Series
        return SearchItemOutput(
            id=str(entity.id),
            type=kind,
            title=entity.get_title(lang),
            year=entity.start_year.value,
            synopsis=entity.get_synopsis(lang),
            poster_path=entity.poster_path.value if entity.poster_path else None,
            backdrop_path=entity.backdrop_path.value if entity.backdrop_path else None,
            genres=entity.get_genres(lang),
        )


__all__ = ["SearchCatalogUseCase"]
