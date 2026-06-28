"""Repository pagination contract shapes.

These are the return types of paginated repository methods, so they
belong in the domain layer alongside the repository interfaces that
declare them — a domain port must not depend on an application-layer
type for its own signature.

``Pagination`` and ``PaginatedResult`` are pure data shapes with no
knowledge of how a cursor is encoded; the opaque-token codec and the
``limit`` clamping constants live in
``building_blocks/application/pagination.py`` because they are
mechanisms consumed by the application, infrastructure, and
presentation layers — not part of the domain contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")


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


__all__ = [
    "PaginatedResult",
    "Pagination",
]
