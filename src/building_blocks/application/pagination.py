"""Cursor-based pagination helpers and DTOs.

Pagination uses an opaque base64-encoded cursor that snapshots the
internal autoincrement ``id`` of the last row returned by the previous
page. The next request echoes the cursor back; the repository decodes
it into a ``WHERE id < :cursor_id`` filter, fetches ``limit + 1`` rows,
and trims the extra row to detect ``has_more``.

Why id-only and not ``(created_at, id)``? An earlier version of this
building block tried to sort by ``(created_at DESC, id DESC)`` so the
order would survive any future feature that sets ``created_at``
explicitly (e.g. backfills). It tripped a SQLite quirk: ``func.now()``
stores values with **second** precision (`'2026-04-11 22:32:13'`) but
SQLAlchemy's `DateTime` serializer binds query parameters with
microsecond precision (`'2026-04-11 22:32:13.000000'`). String-wise,
the second-precision value is **less than** the microsecond-padded one,
so the ``created_at < ?`` branch matched every row and the page never
advanced. Internal autoincrement id doesn't have that problem, is
monotonic with insertion, and matches "newest first" semantics for as
long as ``created_at`` stays server-generated (which is the case
everywhere in HomeFlix today). If a future feature ever needs a
different sort order, the cursor format can change — invalid in-flight
cursors degrade gracefully via the silent-fallback rule.

Invalid or tampered cursors are silently treated as "no cursor — start
from the beginning" so a stale token degrades into the natural starting
point instead of a 400 in the middle of an infinite scroll.

This building block is intentionally tiny and framework-agnostic so
both the application layer (DTOs, use cases) and the infrastructure
layer (SQLAlchemy queries) can share the same shapes.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")

# Default and clamp values for the `limit` query param. Routes typically
# expose `limit` as an int and clamp to ``[1, MAX_PAGE_SIZE]`` before
# handing it to the use case.
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


@dataclass(frozen=True)
class CursorValue:
    """Decoded cursor — the internal autoincrement id of the last row."""

    id: int


@dataclass(frozen=True)
class Pagination:
    """Pagination metadata returned alongside a page of items.

    Attributes:
        next_cursor: Opaque token to pass back as `cursor` on the next
            request. ``None`` when there are no more pages.
        has_more: Convenience flag — equivalent to ``next_cursor is not
            None`` but explicit so clients don't have to infer it.
    """

    next_cursor: str | None
    has_more: bool


@dataclass(frozen=True)
class PaginatedResult(Generic[T]):
    """A page of results with its pagination metadata.

    Attributes:
        items: The page's items.
        pagination: ``Pagination`` for ``next_cursor`` / ``has_more``.
        total_count: Total rows matching the query, or ``None`` when
            the caller did not request it. Computing the total requires
            an extra ``COUNT(*)`` query, so it's opt-in.
    """

    items: list[T]
    pagination: Pagination
    total_count: int | None = None


def encode_cursor(internal_id: int) -> str:
    """Encode the last row's internal id into an opaque cursor string.

    The wire format is the integer rendered as a base64url-encoded
    string. We round-trip through base64 (instead of just stringifying
    the int) so the cursor STAYS opaque to clients — they shouldn't
    treat it as a sortable number.

    Args:
        internal_id: The internal autoincrement primary key of the last
            row of the previous page.

    Returns:
        URL-safe base64 string suitable for use as a query parameter.
    """
    return base64.urlsafe_b64encode(str(internal_id).encode("ascii")).decode("ascii")


def decode_cursor(cursor: str | None) -> CursorValue | None:
    """Decode an opaque cursor back into its internal id.

    Returns ``None`` for an absent or undecodable cursor so callers can
    treat both as "no cursor — start from the beginning". Tampered or
    truncated cursors are silently downgraded instead of raising; the
    cost of an extra page-zero fetch is much smaller than a confusing
    400 in the middle of an infinite scroll.

    Args:
        cursor: The opaque cursor string to decode, or ``None``.

    Returns:
        A ``CursorValue`` on success, or ``None`` when the input is
        empty, malformed, or fails to decode.
    """
    if not cursor:
        return None
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii")).decode("ascii")
        return CursorValue(id=int(raw))
    except (ValueError, UnicodeDecodeError):
        return None


__all__ = [
    "DEFAULT_PAGE_SIZE",
    "MAX_PAGE_SIZE",
    "CursorValue",
    "Pagination",
    "PaginatedResult",
    "decode_cursor",
    "encode_cursor",
]
