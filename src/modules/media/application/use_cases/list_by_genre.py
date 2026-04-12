"""ListByGenreUseCase - paginated mixed (movies + series) listing per genre."""

from src.building_blocks.application.pagination import (
    PaginatedResult,
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

        movies_page = await self._movie_repository.list_paginated_by_genre(
            genre=genre,
            cursor=decoded.movies,
            limit=input_dto.limit,
        )
        series_page = await self._series_repository.list_paginated_by_genre(
            genre=genre,
            cursor=decoded.series,
            limit=input_dto.limit,
        )

        # Tag each entity with its source stream and its source-page
        # index so we can recover the per-item cursor after the merge.
        tagged: list[tuple[str, int, Movie | Series]] = [
            ("movie", index, item) for index, item in enumerate(movies_page.items)
        ] + [("series", index, item) for index, item in enumerate(series_page.items)]
        # Sort by (lowercase title, source index) — the source index
        # tie-breaker matches the SQL `(LOWER(title), id) ASC` order
        # within each stream and gives a stable cross-stream order
        # when two rows share a title.
        tagged.sort(key=lambda triple: (triple[2].title.value.lower(), triple[1]))

        page_items = tagged[: input_dto.limit]

        # has_more is true if either stream still has more rows OR if
        # the merged buffer was larger than the page (we trimmed it).
        has_more = (
            movies_page.pagination.has_more
            or series_page.pagination.has_more
            or len(tagged) > input_dto.limit
        )

        next_cursor = self._compute_next_cursor(
            page_items=page_items,
            movies_page=movies_page,
            series_page=series_page,
            previous_movies_cursor=decoded.movies,
            previous_series_cursor=decoded.series,
            has_more=has_more,
        )

        return ListByGenreOutput(
            items=[self._to_output(kind, item, input_dto.lang) for kind, _, item in page_items],
            next_cursor=next_cursor,
            has_more=has_more,
        )

    @staticmethod
    def _compute_next_cursor(
        *,
        page_items: list[tuple[str, int, Movie | Series]],
        movies_page: PaginatedResult[Movie],
        series_page: PaginatedResult[Series],
        previous_movies_cursor: str | None,
        previous_series_cursor: str | None,
        has_more: bool,
    ) -> str | None:
        """Build the dual cursor for the next page.

        For each stream we look at the highest source-page index of
        any consumed row and pull the corresponding cursor out of the
        repository's ``item_cursors`` list. That cursor is the
        precise resume point — the next call to that repo's
        ``list_paginated_by_genre`` will return rows strictly after
        the consumed item.

        If a stream contributed nothing to the page (no items
        consumed from it), its cursor is left unchanged so the next
        call re-considers the same starting position.
        """
        if not has_more:
            return None

        last_movie_index = max(
            (index for kind, index, _ in page_items if kind == "movie"),
            default=None,
        )
        last_series_index = max(
            (index for kind, index, _ in page_items if kind == "series"),
            default=None,
        )

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
