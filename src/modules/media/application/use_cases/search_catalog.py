"""SearchCatalogUseCase - full-text search across movies and series."""

import asyncio

from src.modules.media.application.dtos.search_dtos import (
    SearchInput,
    SearchItemOutput,
    SearchOutput,
)
from src.modules.media.domain.entities import Movie, Series
from src.modules.media.domain.repositories import MovieRepository, SeriesRepository


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
        movie_repository: MovieRepository,
        series_repository: SeriesRepository,
    ) -> None:
        self._movie_repository = movie_repository
        self._series_repository = series_repository

    async def execute(self, input_dto: SearchInput) -> SearchOutput:
        """Execute the search.

        Args:
            input_dto: Search query, optional filters, lang, limit.

        Returns:
            ``SearchOutput`` with items sorted by relevance and a
            total count.
        """
        # Fetch from both repos in parallel, skipping the excluded
        # type when a filter is active.
        movie_hits: list[tuple[Movie, float]] = []
        series_hits: list[tuple[Series, float]] = []

        if input_dto.media_type == "movie":
            movie_hits = await self._movie_repository.search(
                input_dto.query,
                genre=input_dto.genre,
                year_min=input_dto.year_min,
                year_max=input_dto.year_max,
                limit=input_dto.limit,
            )
        elif input_dto.media_type == "series":
            series_hits = await self._series_repository.search(
                input_dto.query,
                genre=input_dto.genre,
                year_min=input_dto.year_min,
                year_max=input_dto.year_max,
                limit=input_dto.limit,
            )
        else:
            movie_hits, series_hits = await asyncio.gather(
                self._movie_repository.search(
                    input_dto.query,
                    genre=input_dto.genre,
                    year_min=input_dto.year_min,
                    year_max=input_dto.year_max,
                    limit=input_dto.limit,
                ),
                self._series_repository.search(
                    input_dto.query,
                    genre=input_dto.genre,
                    year_min=input_dto.year_min,
                    year_max=input_dto.year_max,
                    limit=input_dto.limit,
                ),
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
