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
from src.modules.media.domain.value_objects import Genre

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
    raw = lang_block.get("genres")
    if not isinstance(raw, list):
        return []
    return [str(g) for g in raw]


async def fetch_genre_rows(
    session: AsyncSession,
    model: Any,
    lang: str,
) -> list[GenreRow]:
    """Project the lightweight genre data of every non-deleted row.

    Reads only ``genres`` and ``localized`` from ``model`` so the
    catalog genres aggregation doesn't pay for joins it doesn't need.
    Each returned ``GenreRow`` pairs the canonical genre list with
    the localized translation for the requested language (or an
    empty list when no translation is present).
    """
    stmt = select(model.genres, model.localized).where(
        model.deleted_at.is_(None),
        model.genres.is_not(None),
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
    title_lower = func.lower(model.title)

    stmt = (
        select(model)
        .where(
            model.deleted_at.is_(None),
            delimited_genres.like(f"%,{genre.value},%"),
        )
        .options(*options)
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
    item_cursors = [encode_title_cursor(row.title, row.id) for row in rows]

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
    "split_genres",
]
