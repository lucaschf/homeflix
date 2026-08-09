"""Shared SQL and parsing helpers for genre-aware repository methods.

Two flavors of helper live here:

- **Column-shape parsers** (``split_genres``, ``localized_genres_for``)
  used by ``list_genre_rows`` to project the raw ``genres`` /
  ``localized`` columns without going through the entity mapper.

- **Query builders + executors** (``fetch_genre_rows``,
  ``fetch_genre_paginated_page``) used by ``list_genre_rows`` and
  ``list_paginated_by_genre`` so the SQLAlchemy boilerplate
  (delimited LIKE filter, lowercased title cursor, fetch N+1 trick,
  per-item cursor population) lives in one place instead of two
  copies that can drift apart.

Lives next to the repos because everything here is tied to the
``genres`` and ``localized`` column shapes — moving the helpers
further away would create a layer that has to be touched whenever
the column format changes.
"""

import json
import re
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any, Literal, TypeVar

from sqlalchemy import and_, func, or_, select, true
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.strategy_options import _AbstractLoad

from src.building_blocks.application.pagination import (
    decode_sort_cursor,
    encode_sort_cursor,
)
from src.building_blocks.domain.pagination import PaginatedResult, Pagination
from src.modules.media.domain.repositories.movie_repository import GenreRow
from src.modules.media.domain.value_objects import CatalogSort, Genre, LocalizedField
from src.shared_kernel.value_objects.library_id import LibraryId

TModel = TypeVar("TModel")
TEntity = TypeVar("TEntity")


def split_genres(raw: str | None) -> list[str]:
    """Parse the comma-separated ``genres`` column into a clean list.

    Returns an empty list for ``None`` or empty input. Whitespace
    around individual genre names is stripped.
    """
    if not raw:
        return []
    return [g.strip() for g in raw.split(",") if g.strip()]


def localized_title_sort_key(model: Any, lang: str) -> Any:
    """SQL sort key ``LOWER(COALESCE(localized[lang].title, title))``.

    Orders a title listing by the localized title when the requested
    language has one, falling back to the canonical (English base)
    ``title`` column. ``lang`` is sanitized to ``[A-Za-z-]`` before
    going into the JSON path; it binds as a parameter, so a stray
    character can only yield a ``NULL`` extraction (→ fallback), never
    SQL injection. SQLite-specific (``json_extract``) — consistent with
    the FTS5 coupling already in the search path.
    """
    safe_lang = re.sub(r"[^A-Za-z-]", "", lang)
    localized_title = func.json_extract(
        model.localized, f'$."{safe_lang}".{LocalizedField.TITLE.value}'
    )
    return func.lower(func.coalesce(localized_title, model.title))


def localized_title_for(localized_json: str | None, base_title: str, lang: str) -> str:
    """Python mirror of ``COALESCE(localized[lang].title, title)``.

    Used to build the title cursor from a fetched row so the encoded
    value matches the SQL ``ORDER BY`` key. Returns the localized title
    when present and non-empty, otherwise ``base_title``.
    """
    if localized_json:
        try:
            data = json.loads(localized_json)
        except (TypeError, ValueError):
            data = None
        if isinstance(data, dict):
            block = data.get(lang)
            if isinstance(block, dict) and block.get(LocalizedField.TITLE.value):
                return str(block[LocalizedField.TITLE.value])
    return base_title


def localized_genres_for(localized_json: str | None, lang: str) -> list[str]:
    """Pull the localized genres array for ``lang`` from the ``localized`` JSON.

    The ``localized`` column is a JSON-encoded dict like
    ``{"pt-BR": {"title": "...", "genres": ["Ação", "Comédia"]}}``.
    This helper safely returns an empty list when the JSON is
    missing, malformed, doesn't carry the requested language, or
    doesn't have a ``genres`` array — the consumer treats an empty
    result as "no translation available" and falls back to the
    canonical names positionally.
    """
    if not localized_json:
        return []
    try:
        data = json.loads(localized_json)
    except (TypeError, ValueError):
        return []
    lang_block = data.get(lang) if isinstance(data, dict) else None
    if not isinstance(lang_block, dict):
        return []
    raw = lang_block.get(LocalizedField.GENRES.value)
    if not isinstance(raw, list):
        return []
    return [str(g) for g in raw]


async def fetch_genre_rows(
    session: AsyncSession,
    model: Any,
    lang: str,
    *,
    allowed_library_ids: Sequence[LibraryId] | None = None,
) -> list[GenreRow]:
    """Project the lightweight genre data of every non-deleted row.

    Reads only ``genres`` and ``localized`` from ``model`` so the
    catalog genres aggregation doesn't pay for joins it doesn't need.
    Each returned ``GenreRow`` pairs the canonical genre list with
    the localized translation for the requested language (or an
    empty list when no translation is present).

    When ``allowed_library_ids`` is non-``None``, the projection is
    restricted to rows whose ``library_id`` is in the supplied set —
    used by the per-profile catalog ACL. ``None`` (default) preserves
    the unfiltered behavior for internal callers.
    """
    stmt = select(model.genres, model.localized).where(
        model.deleted_at.is_(None),
        model.genres.is_not(None),
    )
    if allowed_library_ids is not None:
        stmt = stmt.where(
            model.library_id.in_([library_id.value for library_id in allowed_library_ids])
        )
    result = await session.execute(stmt)
    return [
        GenreRow(
            canonical_genres=split_genres(genres),
            localized_genres=localized_genres_for(localized, lang),
        )
        for genres, localized in result.all()
    ]


# The kind of primary sort key a CatalogSort orders on. ``"id"`` means
# the sort orders on the internal autoincrement id alone (no separate
# primary column) — used by ``recently_added``.
_SortKeyKind = Literal["title", "year", "id"]


@dataclass(frozen=True)
class _GenreSortSpec:
    """How one :class:`CatalogSort` maps onto SQL for the by-genre page.

    Keeping the ORDER BY direction and the primary-key kind in a single
    record — from which the ORDER BY, the cursor ``WHERE`` and the
    per-item cursor key are all derived — guarantees the three stay in
    lockstep. A mismatch between them silently dupes or skips rows across
    pages (the failure only surfaces on page 2+).

    Attributes:
        descending: Whether the primary key (and its ``id`` tie-breaker)
            sort ``DESC``. Flips both the ORDER BY direction and the
            cursor comparison operator.
        key_kind: What the primary key is — ``"title"`` (lowercased
            localized title), ``"year"`` (release year column), or
            ``"id"`` (``recently_added``: order on ``id`` alone).
    """

    descending: bool
    key_kind: _SortKeyKind


# One spec per sort. ``recently_added`` orders on the internal
# autoincrement ``id`` alone (newest first) — id is monotonic with
# insertion within a table, so it matches "newest by created_at" without
# the SQLite ``func.now()`` precision quirk documented in
# ``building_blocks/application/pagination.py``; the cross-stream merge
# in the use case re-orders the two id-DESC streams by ``created_at``.
_GENRE_SORT_SPECS: dict[CatalogSort, _GenreSortSpec] = {
    CatalogSort.TITLE_ASC: _GenreSortSpec(descending=False, key_kind="title"),
    CatalogSort.TITLE_DESC: _GenreSortSpec(descending=True, key_kind="title"),
    CatalogSort.YEAR_ASC: _GenreSortSpec(descending=False, key_kind="year"),
    CatalogSort.YEAR_DESC: _GenreSortSpec(descending=True, key_kind="year"),
    CatalogSort.RECENTLY_ADDED: _GenreSortSpec(descending=True, key_kind="id"),
}


def _primary_sort_column(model: Any, year_column: Any, lang: str, key_kind: _SortKeyKind) -> Any:
    """Primary ORDER BY / cursor column for ``key_kind`` (``None`` for id-only).

    Returns a SQLAlchemy ``ColumnElement`` (untyped ``Any`` here to match
    the surrounding query builders) or ``None`` when the sort orders on
    ``id`` alone.
    """
    if key_kind == "title":
        return localized_title_sort_key(model, lang)
    if key_kind == "year":
        return year_column
    return None


def _row_sort_key(row: Any, year_column: Any, lang: str, key_kind: _SortKeyKind) -> str:
    """Render a fetched row's primary key to the cursor's string form."""
    if key_kind == "title":
        return localized_title_for(row.localized, row.title, lang).lower()
    if key_kind == "year":
        return str(getattr(row, year_column.key))
    return ""


async def fetch_genre_paginated_page(
    *,
    session: AsyncSession,
    model: Any,
    mapper_to_entity: Callable[[Any], TEntity] | Callable[[Any], Awaitable[TEntity]],
    options: Sequence[_AbstractLoad],
    genre: Genre,
    cursor: str | None,
    limit: int,
    year_column: Any,
    sort: CatalogSort = CatalogSort.TITLE_ASC,
    lang: str = "en",
    allowed_library_ids: Sequence[LibraryId] | None = None,
) -> PaginatedResult[TEntity]:
    """Run one page of the by-genre listing for ``model`` under ``sort``.

    Wraps the duplicated SQL boilerplate that ``list_paginated_by_genre``
    needs in both repositories: the delimited LIKE filter that avoids
    substring matches, the sort-aware composite ``(sort_key, id)`` cursor,
    the N+1 fetch trick to detect ``has_more``, and the parallel
    ``item_cursors`` list that the catalog by-genre use case needs to
    advance partial consumption.

    The ORDER BY, the cursor ``WHERE`` and the per-item cursor key all
    derive from a single :class:`_GenreSortSpec` keyed by ``sort`` so the
    three can't drift out of lockstep.

    Args:
        session: AsyncSession to execute against.
        model: SQLAlchemy ORM model class (``MovieModel`` or
            ``SeriesModel``).
        mapper_to_entity: Callable that converts a single ``model``
            instance into the corresponding domain entity. Sync only —
            the existing mappers don't need IO and an async signature
            would just add ceremony.
        options: SQLAlchemy load options to apply to the select
            (e.g. ``selectinload`` of relationships). Empty sequence
            is fine.
        genre: Canonical genre value object to filter by.
        cursor: Opaque sort cursor from the previous page, or ``None``
            for the first page. Invalid cursors — including one minted
            under a different ``sort`` — silently fall back to the first
            page.
        limit: Page size. The query fetches ``limit + 1`` rows and
            trims the sentinel.
        year_column: The model's release-year column (``MovieModel.year``
            / ``SeriesModel.start_year``) used by the ``year_*`` sorts.
        sort: The ordering to apply. Defaults to ``TITLE_ASC`` so the
            behavior is byte-identical to the pre-sort endpoint.
        lang: Language whose localized title drives the title sort order
            (falls back to the canonical ``title`` when absent).
        allowed_library_ids: Optional per-profile ACL filter. When
            non-``None``, rows are restricted to those whose
            ``library_id`` is in the supplied set. ``None`` (default)
            applies no library filter.

    Returns:
        ``PaginatedResult`` with mapped entities, pagination
        metadata, and the per-item cursor list.
    """
    spec = _GENRE_SORT_SPECS[sort]
    decoded = decode_sort_cursor(cursor, expected_sort=sort.value)

    # Wrap the column with delimiters so a substring search can't
    # false-positive: "Action" must NOT match "Reaction" or
    # "Action Adventure". The matching pattern wraps the genre value
    # the same way.
    delimited_genres = func.concat(",", func.coalesce(model.genres, ""), ",")

    stmt = (
        select(model)
        .where(
            model.deleted_at.is_(None),
            delimited_genres.like(f"%,{genre.value},%"),
        )
        .options(*options)
    )

    if allowed_library_ids is not None:
        stmt = stmt.where(
            model.library_id.in_([library_id.value for library_id in allowed_library_ids])
        )

    primary = _primary_sort_column(model, year_column, lang, spec.key_kind)

    if decoded is not None:
        stmt = stmt.where(_cursor_predicate(model, primary, spec, decoded))

    if primary is None:
        stmt = stmt.order_by(model.id.desc())
    elif spec.descending:
        stmt = stmt.order_by(primary.desc(), model.id.desc())
    else:
        stmt = stmt.order_by(primary.asc(), model.id.asc())
    stmt = stmt.limit(limit + 1)

    result = await session.execute(stmt)
    rows = list(result.scalars().all())

    has_more = len(rows) > limit
    if has_more:
        rows = rows[:limit]

    # Per-item cursor list — the catalog by-genre use case may
    # consume only a prefix of this page after merging with the
    # other media stream, so each item carries its own resume token.
    item_cursors = [
        encode_sort_cursor(sort.value, _row_sort_key(row, year_column, lang, spec.key_kind), row.id)
        for row in rows
    ]

    next_cursor: str | None = None
    if has_more and rows:
        next_cursor = item_cursors[-1]

    return PaginatedResult(
        items=[mapper_to_entity(row) for row in rows],  # type: ignore[misc]
        pagination=Pagination(next_cursor=next_cursor, has_more=has_more),
        total_count=None,
        item_cursors=item_cursors,
    )


def _cursor_predicate(
    model: Any,
    primary: Any,
    spec: _GenreSortSpec,
    decoded: Any,
) -> Any:
    """Build the "strictly after the cursor row" predicate for one sort.

    For an ``id``-only sort (``recently_added``) this is a bare
    ``id < cursor_id``. For a composite ``(key, id)`` sort it is the
    standard row-value comparison expanded into an OR with the ``id``
    tie-breaker, direction-aware. A cursor ``key`` that fails to parse
    (tampered) degrades to "no predicate" so the request restarts from
    page 1 rather than raising mid-scroll.
    """
    if primary is None:
        # recently_added: id DESC, so "after" means a smaller id.
        return model.id < decoded.id
    try:
        pivot: Any = int(decoded.key) if spec.key_kind == "year" else decoded.key
    except ValueError:
        # Tampered/unparseable key — ignore the cursor (a no-op TRUE
        # predicate) so the request restarts from page 1 rather than
        # raising mid-scroll.
        return true()
    if spec.descending:
        return or_(primary < pivot, and_(primary == pivot, model.id < decoded.id))
    return or_(primary > pivot, and_(primary == pivot, model.id > decoded.id))


__all__ = [
    "fetch_genre_paginated_page",
    "fetch_genre_rows",
    "localized_genres_for",
    "localized_title_for",
    "localized_title_sort_key",
    "split_genres",
]
