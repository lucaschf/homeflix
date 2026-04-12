"""ListByGenreUseCase - paginated mixed (movies + series) listing per genre."""

import asyncio
from dataclasses import dataclass
from typing import Literal, TypeVar

from src.building_blocks.application.pagination import (
    DualCursorValue,
    PaginatedResult,
    Pagination,
    decode_dual_cursor,
    encode_dual_cursor,
)
from src.modules.media.application.dtos.catalog_dtos import (
    CatalogItemOutput,
    ListByGenreInput,
    ListByGenreOutput,
)
from src.modules.media.domain.entities import Movie, Series
from src.modules.media.domain.repositories import MovieRepository, SeriesRepository
from src.modules.media.domain.value_objects import Genre

_T = TypeVar("_T")


def _empty_page(_element_type: type[_T]) -> PaginatedResult[_T]:
    """Build a no-op ``PaginatedResult`` for a stream that was skipped.

    Used when the media-type filter excludes one side of the merge —
    the missing stream is replaced by an empty page so the sort and
    cursor-advancement logic below stays linear instead of sprouting
    a second code path for the "only one stream" case. The
    ``_element_type`` argument is present only so mypy can bind the
    generic parameter at the call site — it's not used at runtime.
    """
    return PaginatedResult(
        items=[],
        pagination=Pagination(next_cursor=None, has_more=False),
        item_cursors=[],
    )


@dataclass(frozen=True)
class _MergedItem:
    """One row of the merged movies + series stream.

    Carries the source-page index alongside the entity so the use
    case can pull the corresponding cursor out of the right
    repository's ``item_cursors`` after the merge sort. Internal to
    this module — the public API still returns ``CatalogItemOutput``.
    """

    kind: Literal["movie", "series"]
    source_index: int
    entity: Movie | Series


class ListByGenreUseCase:
    """Paginated mixed listing of movies + series for a single genre.

    Both repositories are queried in parallel via their own
    ``list_paginated_by_genre`` method (sorted by ``LOWER(title), id``),
    the two streams are merged in Python by title, the merged result
    is trimmed to the requested page size, and a dual cursor is
    composed from the position each stream is left at.

    Cursor advancement is "consumed-aware": each repository populates
    a parallel ``item_cursors`` list on its ``PaginatedResult`` with
    one cursor per item — the cursor that resumes strictly after that
    specific row. The use case picks the cursor of the last consumed
    row from each stream. If a stream contributed nothing to the
    page (because the other stream's titles all came earlier), its
    cursor stays unchanged so the next call re-considers the same
    first row in the merge.

    Per-item cursors are necessary because the page may be a strict
    PREFIX of one stream's full fetched buffer — using the page's
    own ``next_cursor`` would jump past rows that the merge left for
    the next page.

    Each repository fetches up to ``limit`` items independently. In
    the worst case (one stream has nothing in the genre) the merge
    over-fetches by ``limit`` rows from the empty stream — acceptable
    because the LIKE filter on a non-matching genre is essentially
    free.
    """

    def __init__(
        self,
        movie_repository: MovieRepository,
        series_repository: SeriesRepository,
    ) -> None:
        self._movie_repository = movie_repository
        self._series_repository = series_repository

    async def execute(self, input_dto: ListByGenreInput) -> ListByGenreOutput:
        """Execute the use case.

        Args:
            input_dto: ``genre`` (canonical id), ``cursor`` (opaque
                dual-stream token), ``limit``, and ``lang``.

        Returns:
            ``ListByGenreOutput`` carrying the merged page of catalog
            items + the dual cursor for the next page.
        """
        decoded = decode_dual_cursor(input_dto.cursor)
        genre = Genre(input_dto.genre)

        # Both repository calls are independent I/O — issue them
        # concurrently via `asyncio.gather` so the by-genre endpoint
        # only waits for the slower of the two queries instead of
        # serializing them. The DI container hands each repository
        # its own AsyncSession (Factory provider), so there's no
        # session contention to worry about.
        #
        # When ``media_type`` restricts the stream to one side, the
        # excluded repo is skipped entirely and a synthetic empty
        # page stands in for it so the merge / cursor logic below
        # stays unchanged.
        movies_page, series_page = await self._fetch_pages(
            genre=genre,
            decoded=decoded,
            limit=input_dto.limit,
            media_type=input_dto.media_type,
        )

        # Tag each entity with its source stream and its source-page
        # index so we can recover the per-item cursor after the merge.
        tagged: list[_MergedItem] = [
            _MergedItem(kind="movie", source_index=index, entity=item)
            for index, item in enumerate(movies_page.items)
        ] + [
            _MergedItem(kind="series", source_index=index, entity=item)
            for index, item in enumerate(series_page.items)
        ]
        # Sort by (lowercase title, source index) — the source index
        # tie-breaker matches the SQL `(LOWER(title), id) ASC` order
        # within each stream and gives a stable cross-stream order
        # when two rows share a title.
        tagged.sort(key=lambda mi: (mi.entity.title.value.lower(), mi.source_index))

        page_items = tagged[: input_dto.limit]

        # Track the highest consumed source-page index per stream
        # while we walk the page once. The next-cursor computation
        # below uses these directly instead of re-scanning the page.
        last_movie_index: int | None = None
        last_series_index: int | None = None
        for item in page_items:
            if item.kind == "movie":
                last_movie_index = item.source_index
            else:
                last_series_index = item.source_index

        # has_more is true if either stream still has more rows OR if
        # the merged buffer was larger than the page (we trimmed it).
        has_more = (
            movies_page.pagination.has_more
            or series_page.pagination.has_more
            or len(tagged) > input_dto.limit
        )

        next_cursor = self._compute_next_cursor(
            movies_page=movies_page,
            series_page=series_page,
            previous_movies_cursor=decoded.movies,
            previous_series_cursor=decoded.series,
            last_movie_index=last_movie_index,
            last_series_index=last_series_index,
            has_more=has_more,
        )

        return ListByGenreOutput(
            items=[self._to_output(mi.kind, mi.entity, input_dto.lang) for mi in page_items],
            next_cursor=next_cursor,
            has_more=has_more,
        )

    async def _fetch_pages(
        self,
        *,
        genre: Genre,
        decoded: DualCursorValue,
        limit: int,
        media_type: Literal["movie", "series"] | None,
    ) -> tuple[PaginatedResult[Movie], PaginatedResult[Series]]:
        """Fetch the movie and series pages, honoring the media-type filter.

        Both repos are awaited concurrently via ``asyncio.gather``
        when no filter is active. When ``media_type`` excludes a
        stream, only the surviving repo is called and an empty
        ``PaginatedResult`` stands in for the other — preserving the
        caller's ``(movies, series)`` tuple shape and the "previous
        cursor stays put if nothing is consumed" semantics of the
        merge sort.
        """
        if media_type == "movie":
            movies_page = await self._movie_repository.list_paginated_by_genre(
                genre=genre,
                cursor=decoded.movies,
                limit=limit,
            )
            return movies_page, _empty_page(Series)
        if media_type == "series":
            series_page = await self._series_repository.list_paginated_by_genre(
                genre=genre,
                cursor=decoded.series,
                limit=limit,
            )
            return _empty_page(Movie), series_page
        return await asyncio.gather(
            self._movie_repository.list_paginated_by_genre(
                genre=genre,
                cursor=decoded.movies,
                limit=limit,
            ),
            self._series_repository.list_paginated_by_genre(
                genre=genre,
                cursor=decoded.series,
                limit=limit,
            ),
        )

    @staticmethod
    def _compute_next_cursor(
        *,
        movies_page: PaginatedResult[Movie],
        series_page: PaginatedResult[Series],
        previous_movies_cursor: str | None,
        previous_series_cursor: str | None,
        last_movie_index: int | None,
        last_series_index: int | None,
        has_more: bool,
    ) -> str | None:
        """Build the dual cursor for the next page from the pre-computed last indices.

        For each stream the caller has already tracked the highest
        consumed source-page index (or ``None`` if nothing was
        consumed from that stream). We pull the matching cursor out
        of the repository's ``item_cursors`` list. If a stream
        contributed nothing to the page, its cursor is left unchanged
        so the next call re-considers the same starting position —
        guaranteeing no item is skipped or duplicated across pages.
        """
        if not has_more:
            return None

        next_movies_cursor = (
            movies_page.item_cursors[last_movie_index]
            if last_movie_index is not None and movies_page.item_cursors is not None
            else previous_movies_cursor
        )
        next_series_cursor = (
            series_page.item_cursors[last_series_index]
            if last_series_index is not None and series_page.item_cursors is not None
            else previous_series_cursor
        )

        return encode_dual_cursor(next_movies_cursor, next_series_cursor)

    @staticmethod
    def _to_output(kind: str, item: Movie | Series, lang: str) -> CatalogItemOutput:
        """Convert a movie/series entity into the catalog row DTO."""
        if isinstance(item, Movie):
            return CatalogItemOutput(
                id=str(item.id),
                type=kind,
                title=item.get_title(lang),
                year=item.year.value,
                synopsis=item.get_synopsis(lang),
                poster_path=item.poster_path.value if item.poster_path else None,
                backdrop_path=item.backdrop_path.value if item.backdrop_path else None,
                genres=item.get_genres(lang),
            )
        # Series
        return CatalogItemOutput(
            id=str(item.id),
            type=kind,
            title=item.get_title(lang),
            year=item.start_year.value,
            synopsis=item.get_synopsis(lang),
            poster_path=item.poster_path.value if item.poster_path else None,
            backdrop_path=item.backdrop_path.value if item.backdrop_path else None,
            genres=item.get_genres(lang),
        )


__all__ = ["ListByGenreUseCase"]
