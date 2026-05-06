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
import binascii
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
class TitleCursorValue:
    """Decoded cursor for listings sorted by ``(LOWER(title), id)``.

    Used by the catalog "by genre" endpoint where rows are surfaced
    alphabetically rather than by insertion order. The composite key
    is necessary because two rows can share the same title and the
    sort would otherwise be unstable across pages — the ``id``
    tie-breaker guarantees a deterministic order.
    """

    title: str
    id: int


@dataclass(frozen=True)
class DualCursorValue:
    """Decoded cursor that bundles two independent stream cursors.

    The catalog by-genre endpoint queries movies and series in
    parallel and merges the two streams alphabetically by title; each
    stream advances at its own pace, so the page's "next cursor" must
    carry both stream positions. ``movies`` and ``series`` are the
    raw, still-opaque per-stream cursor strings — neither is decoded
    by this building block; the use case forwards them back to the
    repositories untouched.
    """

    movies: str | None
    series: str | None


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
        item_cursors: Parallel to ``items`` — cursor that resumes
            strictly after that item. Populated only by repository
            methods whose consumers need to advance through a partial
            prefix of the page (e.g. the catalog "by genre" listing,
            which fetches movies and series in parallel and may use
            only some items from each before the merged page is full).
            For straight-through consumers that always exhaust the
            whole page, ``pagination.next_cursor`` is enough and this
            field stays ``None``.
    """

    items: list[T]
    pagination: Pagination
    total_count: int | None = None
    item_cursors: list[str] | None = None


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


# Separator used inside the title cursor's encoded payload. The
# raw form is `<title_lower>\x1f<id>` so a literal `|` (or any other
# printable separator) inside a title can't collide with the
# delimiter. ASCII 0x1F is the "unit separator" control character —
# it's not part of any practical title.
_TITLE_CURSOR_SEP = "\x1f"


def encode_title_cursor(title: str, internal_id: int) -> str:
    """Encode a ``(title, id)`` pair as an opaque title-sorted cursor.

    The title is lowercased before encoding so the cursor matches the
    repository's ``LOWER(title)`` sort key — pagination must use the
    exact same comparison the SQL ``ORDER BY`` uses or rows can be
    skipped or repeated across pages.

    Args:
        title: The title of the last row of the previous page. Will
            be lowercased internally.
        internal_id: The internal autoincrement id of the same row.
            Used as the tie-breaker when two rows share a title.

    Returns:
        URL-safe base64 string suitable for use as a query parameter.
    """
    raw = f"{title.lower()}{_TITLE_CURSOR_SEP}{internal_id}"
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii")


def decode_title_cursor(cursor: str | None) -> TitleCursorValue | None:
    """Decode a title-sorted opaque cursor back into ``(title, id)``.

    Returns ``None`` for absent or malformed cursors so the caller
    silently falls back to the first page (same contract as
    ``decode_cursor``).
    """
    if not cursor:
        return None
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8")
        title, id_str = raw.split(_TITLE_CURSOR_SEP, 1)
        return TitleCursorValue(title=title, id=int(id_str))
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return None


# Separator for the dual-cursor wire format. Same rationale as
# `_TITLE_CURSOR_SEP` — using a control character keeps the parser
# robust against any payload bytes the inner stream cursors might
# contain.
_DUAL_CURSOR_SEP = "\x1e"  # ASCII record separator


def encode_dual_cursor(movies: str | None, series: str | None) -> str:
    """Bundle two independent stream cursors into one opaque token.

    Either side can be ``None``, meaning "that stream is exhausted /
    has not been started". The encoder writes empty strings for those
    so the parser can round-trip them deterministically.
    """
    raw = f"{movies or ''}{_DUAL_CURSOR_SEP}{series or ''}"
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii")


def decode_dual_cursor(cursor: str | None) -> DualCursorValue:
    """Decode a dual cursor; an absent or malformed token decodes to (None, None).

    The return type is intentionally non-optional — callers always
    get a ``DualCursorValue`` and can check ``.movies`` / ``.series``
    individually. This keeps the use-case happy path linear (no
    extra ``if cursor is not None`` branch).
    """
    if not cursor:
        return DualCursorValue(movies=None, series=None)
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8")
        movies, series = raw.split(_DUAL_CURSOR_SEP, 1)
        return DualCursorValue(
            movies=movies or None,
            series=series or None,
        )
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return DualCursorValue(movies=None, series=None)


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
    except (binascii.Error, UnicodeDecodeError, ValueError):
        # `binascii.Error` is technically a subclass of `ValueError` in
        # CPython today, so the trailing `ValueError` would catch it
        # too — listing it explicitly documents the contract for the
        # next reader and protects against any future Python release
        # that might split the hierarchy.
        return None


__all__ = [
    "DEFAULT_PAGE_SIZE",
    "MAX_PAGE_SIZE",
    "CursorValue",
    "DualCursorValue",
    "Pagination",
    "PaginatedResult",
    "TitleCursorValue",
    "decode_cursor",
    "decode_dual_cursor",
    "decode_title_cursor",
    "encode_cursor",
    "encode_dual_cursor",
    "encode_title_cursor",
]
