"""ListByGenreUseCase - paginated mixed (movies + series) listing per genre."""

import asyncio
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from functools import cmp_to_key
from typing import Any, TypeVar

from src.building_blocks.application.pagination import (
    DualCursorValue,
    decode_dual_cursor,
    encode_dual_cursor,
)
from src.building_blocks.domain.pagination import PaginatedResult, Pagination
from src.modules.media.application.dtos.catalog_dtos import (
    CatalogItemOutput,
    ListByGenreInput,
    ListByGenreOutput,
)
from src.modules.media.application.ports.profile_library_access_port import (
    ProfileLibraryAccessPort,
)
from src.modules.media.application.unit_of_work import MediaUnitOfWorkFactory
from src.modules.media.domain.entities import Movie, Series
from src.modules.media.domain.value_objects import CatalogSort, Genre
from src.shared_kernel.value_objects import MediaType
from src.shared_kernel.value_objects.library_id import LibraryId

_T = TypeVar("_T")

# Sorts whose primary key descends. Kept as a set so the merge
# comparator and any future reader agree on the direction of each sort
# in one place.
_DESCENDING_SORTS = frozenset(
    {CatalogSort.TITLE_DESC, CatalogSort.YEAR_DESC, CatalogSort.RECENTLY_ADDED}
)


def _merge_primary_key(entity: Movie | Series, sort: CatalogSort, lang: str) -> Any:
    """Primary sort key for one entity, matching the SQL ORDER BY key.

    Mirrors ``_GenreSortSpec`` on the repository side: title sorts
    compare the lowercased localized title, year sorts the release year
    (movie ``year`` / series ``start_year``), and ``recently_added`` the
    ``created_at`` timestamp — the cross-stream analogue of each stream's
    ``id DESC`` order (ids from the two tables aren't comparable, so a
    real timestamp is required; same rationale as
    ``ListRecentlyAddedCatalogUseCase``).
    """
    if sort in (CatalogSort.TITLE_ASC, CatalogSort.TITLE_DESC):
        return (entity.get_title(lang) or "").lower()
    if sort in (CatalogSort.YEAR_ASC, CatalogSort.YEAR_DESC):
        return entity.year.value if isinstance(entity, Movie) else entity.start_year.value
    return entity.created_at


def _merge_comparator(
    sort: CatalogSort, lang: str
) -> Callable[["_MergedItem", "_MergedItem"], int]:
    """Build a stable comparator matching each stream's own SQL order.

    Compares the primary key in the sort's direction and breaks ties on
    ``source_index`` *ascending* regardless of direction. Each stream
    arrives already in its SQL order, so preserving source order on a
    primary-key tie keeps the merged sequence consistent with each
    stream's per-item cursor. A descending primary must NOT simply
    reverse the whole sort key — that would flip the source-order
    tie-break too and dupe/skip rows across the page boundary (the bug
    only surfaces on page 2+). When both the primary key and the source
    index tie (two streams contributing the same key at the same depth),
    the comparator returns 0 and Python's stable sort keeps movies before
    series — deterministic across pages.
    """
    descending = sort in _DESCENDING_SORTS

    def compare(a: "_MergedItem", b: "_MergedItem") -> int:
        ka = _merge_primary_key(a.entity, sort, lang)
        kb = _merge_primary_key(b.entity, sort, lang)
        if ka != kb:
            base = -1 if ka < kb else 1
            return -base if descending else base
        return (a.source_index > b.source_index) - (a.source_index < b.source_index)

    return compare


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

    kind: MediaType
    source_index: int
    entity: Movie | Series


class ListByGenreUseCase:
    """Paginated mixed listing of movies + series for a single genre.

    Both repositories are queried in parallel via their own
    ``list_paginated_by_genre`` method under the requested ``sort``
    (title / year / recently-added, each ending in ``id`` as the
    tie-breaker); the two streams are merged in Python by the same sort
    key, the merged result is trimmed to the requested page size, and a
    dual cursor is composed from the position each stream is left at. The
    Python merge key and its direction mirror the SQL order exactly (see
    ``_merge_comparator``) so partial-prefix cursor advancement stays
    correct for every sort.

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
        uow_factory: MediaUnitOfWorkFactory,
        profile_library_access: ProfileLibraryAccessPort,
    ) -> None:
        self._uow_factory = uow_factory
        self._profile_library_access = profile_library_access

    async def execute(self, input_dto: ListByGenreInput) -> ListByGenreOutput:
        """Execute the use case.

        Args:
            input_dto: ``profile_id``, ``genre`` (canonical id),
                ``cursor`` (opaque dual-stream token), ``limit``, and
                ``lang``.

        Returns:
            ``ListByGenreOutput`` carrying the merged page of catalog
            items + the dual cursor for the next page. A deny-all
            profile yields an empty page without opening a UoW.
        """
        allowed = await self._profile_library_access.find_for_profile(input_dto.profile_id)
        if not allowed:
            return ListByGenreOutput(items=[], next_cursor=None, has_more=False)

        decoded = decode_dual_cursor(input_dto.cursor)
        genre = Genre(input_dto.genre)

        # When ``media_type`` restricts the stream to one side, the
        # excluded repo is skipped entirely and a synthetic empty
        # page stands in for it so the merge / cursor logic below
        # stays unchanged.
        movies_page, series_page = await self._fetch_pages(
            genre=genre,
            decoded=decoded,
            limit=input_dto.limit,
            media_type=input_dto.media_type,
            sort=input_dto.sort,
            lang=input_dto.lang,
            allowed_library_ids=allowed,
        )

        # Tag each entity with its source stream and its source-page
        # index so we can recover the per-item cursor after the merge.
        tagged: list[_MergedItem] = [
            _MergedItem(kind=MediaType.MOVIE, source_index=index, entity=item)
            for index, item in enumerate(movies_page.items)
        ] + [
            _MergedItem(kind=MediaType.SERIES, source_index=index, entity=item)
            for index, item in enumerate(series_page.items)
        ]
        # Merge the two already-sorted streams under the requested order.
        # The comparator applies the sort's direction to the primary key
        # and breaks ties on ``source_index`` (ascending) so each stream
        # stays in the exact order its SQL query — and therefore its
        # per-item cursor — produced. See ``_merge_comparator``.
        tagged.sort(key=cmp_to_key(_merge_comparator(input_dto.sort, input_dto.lang)))

        page_items = tagged[: input_dto.limit]

        # Track the highest consumed source-page index per stream
        # while we walk the page once. The next-cursor computation
        # below uses these directly instead of re-scanning the page.
        last_movie_index: int | None = None
        last_series_index: int | None = None
        for item in page_items:
            if item.kind is MediaType.MOVIE:
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
        media_type: MediaType | None,
        sort: CatalogSort,
        lang: str,
        allowed_library_ids: Sequence[LibraryId],
    ) -> tuple[PaginatedResult[Movie], PaginatedResult[Series]]:
        """Fetch the movie and series pages, honoring the media-type filter.

        Both repos are awaited concurrently via ``asyncio.gather`` when
        no filter is active; each branch opens its own ``MediaUnitOfWork``
        so the two queries run on independent sessions (SQLAlchemy's
        AsyncSession forbids concurrent execution on the same session).
        When ``media_type`` excludes a stream, only the surviving repo
        is called and an empty ``PaginatedResult`` stands in for the
        other — preserving the caller's ``(movies, series)`` tuple
        shape and the "previous cursor stays put if nothing is consumed"
        semantics of the merge sort.
        """
        if media_type is MediaType.MOVIE:
            async with self._uow_factory() as uow:
                movies_page = await uow.movies.list_paginated_by_genre(
                    genre=genre,
                    cursor=decoded.movies,
                    limit=limit,
                    sort=sort,
                    lang=lang,
                    allowed_library_ids=allowed_library_ids,
                )
            return movies_page, _empty_page(Series)
        if media_type is MediaType.SERIES:
            async with self._uow_factory() as uow:
                series_page = await uow.series.list_paginated_by_genre(
                    genre=genre,
                    cursor=decoded.series,
                    limit=limit,
                    sort=sort,
                    lang=lang,
                    allowed_library_ids=allowed_library_ids,
                )
            return _empty_page(Movie), series_page
        return await asyncio.gather(
            self._fetch_movies_page(
                genre=genre,
                cursor=decoded.movies,
                limit=limit,
                sort=sort,
                lang=lang,
                allowed_library_ids=allowed_library_ids,
            ),
            self._fetch_series_page(
                genre=genre,
                cursor=decoded.series,
                limit=limit,
                sort=sort,
                lang=lang,
                allowed_library_ids=allowed_library_ids,
            ),
        )

    async def _fetch_movies_page(
        self,
        *,
        genre: Genre,
        cursor: str | None,
        limit: int,
        sort: CatalogSort,
        lang: str,
        allowed_library_ids: Sequence[LibraryId],
    ) -> PaginatedResult[Movie]:
        async with self._uow_factory() as uow:
            return await uow.movies.list_paginated_by_genre(
                genre=genre,
                cursor=cursor,
                limit=limit,
                sort=sort,
                lang=lang,
                allowed_library_ids=allowed_library_ids,
            )

    async def _fetch_series_page(
        self,
        *,
        genre: Genre,
        cursor: str | None,
        limit: int,
        sort: CatalogSort,
        lang: str,
        allowed_library_ids: Sequence[LibraryId],
    ) -> PaginatedResult[Series]:
        async with self._uow_factory() as uow:
            return await uow.series.list_paginated_by_genre(
                genre=genre,
                cursor=cursor,
                limit=limit,
                sort=sort,
                lang=lang,
                allowed_library_ids=allowed_library_ids,
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
    def _to_output(kind: MediaType, item: Movie | Series, lang: str) -> CatalogItemOutput:
        """Convert a movie/series entity into the catalog row DTO."""
        if isinstance(item, Movie):
            return CatalogItemOutput(
                id=str(item.id),
                type=kind.value,
                title=item.get_title(lang),
                year=item.year.value,
                synopsis=item.get_synopsis(lang),
                poster_path=item.get_poster_path(lang),
                backdrop_path=item.get_backdrop_path(lang),
                genres=item.get_genres(lang),
            )
        # Series
        return CatalogItemOutput(
            id=str(item.id),
            type=kind,
            title=item.get_title(lang),
            year=item.start_year.value,
            synopsis=item.get_synopsis(lang),
            poster_path=item.get_poster_path(lang),
            backdrop_path=item.get_backdrop_path(lang),
            genres=item.get_genres(lang),
        )


__all__ = ["ListByGenreUseCase"]
