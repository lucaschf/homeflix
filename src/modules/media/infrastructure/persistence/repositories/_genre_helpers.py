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
from typing import Any, TypeVar

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.strategy_options import _AbstractLoad

from src.building_blocks.application.pagination import (
    PaginatedResult,
    Pagination,
    decode_title_cursor,
    encode_title_cursor,
)
from src.modules.media.domain.repositories.movie_repository import GenreRow
from src.modules.media.domain.value_objects import Genre, LocalizedField
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


async def fetch_genre_paginated_page(
    *,
    session: AsyncSession,
    model: Any,
    mapper_to_entity: Callable[[Any], TEntity] | Callable[[Any], Awaitable[TEntity]],
    options: Sequence[_AbstractLoad],
    genre: Genre,
    cursor: str | None,
    limit: int,
    lang: str = "en",
    allowed_library_ids: Sequence[LibraryId] | None = None,
) -> PaginatedResult[TEntity]:
    """Run one page of the title-sorted by-genre listing for ``model``.

    Wraps the duplicated SQL boilerplate that ``list_paginated_by_genre``
    needs in both repositories: the delimited LIKE filter that avoids
    substring matches, the ``LOWER(title), id`` cursor, the N+1 fetch
    trick to detect ``has_more``, and the parallel ``item_cursors``
    list that the catalog by-genre use case needs to advance partial
    consumption.

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
        cursor: Opaque title cursor from the previous page, or
            ``None`` for the first page. Invalid cursors silently
            fall back to the first page.
        limit: Page size. The query fetches ``limit + 1`` rows and
            trims the sentinel.
        lang: Language whose localized title drives the sort order
            (falls back to the canonical ``title`` when absent).
        allowed_library_ids: Optional per-profile ACL filter. When
            non-``None``, rows are restricted to those whose
            ``library_id`` is in the supplied set. ``None`` (default)
            applies no library filter.

    Returns:
        ``PaginatedResult`` with mapped entities, pagination
        metadata, and the per-item cursor list.
    """
    decoded = decode_title_cursor(cursor)

    # Wrap the column with delimiters so a substring search can't
    # false-positive: "Action" must NOT match "Reaction" or
    # "Action Adventure". The matching pattern wraps the genre value
    # the same way.
    delimited_genres = func.concat(",", func.coalesce(model.genres, ""), ",")
    title_lower = localized_title_sort_key(model, lang)

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

    if decoded is not None:
        # Composite ascending: anything strictly after the cursor
        # row in the (title, id) merge order. The OR + tie-breaker
        # is the same shape as a stable cursor for any composite
        # sort.
        stmt = stmt.where(
            or_(
                title_lower > decoded.title,
                and_(title_lower == decoded.title, model.id > decoded.id),
            )
        )

    stmt = stmt.order_by(title_lower.asc(), model.id.asc()).limit(limit + 1)

    result = await session.execute(stmt)
    rows = list(result.scalars().all())

    has_more = len(rows) > limit
    if has_more:
        rows = rows[:limit]

    # Per-item cursor list — the catalog by-genre use case may
    # consume only a prefix of this page after merging with the
    # other media stream, so each item carries its own resume token.
    item_cursors = [
        encode_title_cursor(localized_title_for(row.localized, row.title, lang), row.id)
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


__all__ = [
    "fetch_genre_paginated_page",
    "fetch_genre_rows",
    "localized_genres_for",
    "localized_title_for",
    "localized_title_sort_key",
    "split_genres",
]
