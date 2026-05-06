"""API Response Envelope helpers (v3.0 standard).

All successful HTTP responses in the project share the same envelope
so that clients can parse them with one code path. See
`docs/standards/api-response-standard-rest-v3.md` for the full spec.

Two shapes are supported:

- **Single resource** — ``{"type": "<resource>", "data": {...}}``
- **Collection** — ``{"type": "list", "data": [...], "metadata": {...}}``

``metadata`` is optional and carries pagination, applied filters, and
non-breaking extras (e.g. ``total_count``). Pagination is nested inside
``metadata`` to match the project's existing clients; the standard doc
describes a top-level placement that can be adopted in a future major.
"""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class Pagination:
    """Pagination descriptor for list responses.

    Cursor-based pagination is the default; ``total`` is opt-in since
    ``COUNT(*)`` is costly on large tables.

    Attributes:
        has_more: Whether the next page exists.
        next_cursor: Opaque cursor for the next page (if any).
        prev_cursor: Opaque cursor for the previous page (if any).
        total: Total item count when explicitly requested.
    """

    has_more: bool
    next_cursor: str | None = None
    prev_cursor: str | None = None
    total: int | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize, omitting None-valued fields.

        Returns:
            Dictionary suitable for JSON serialization.
        """
        result: dict[str, Any] = {"has_more": self.has_more}
        if self.next_cursor is not None:
            result["next_cursor"] = self.next_cursor
        if self.prev_cursor is not None:
            result["prev_cursor"] = self.prev_cursor
        if self.total is not None:
            result["total"] = self.total
        return result


def api_single(resource_type: str, data: Any) -> dict[str, Any]:
    """Wrap a single-resource payload in the standard envelope.

    Args:
        resource_type: Stable resource identifier exposed to clients
            (e.g. ``"movie"``, ``"library"``, ``"preferences"``).
        data: The resource payload (already serialized — typically the
            output of ``dataclasses.asdict`` on a use-case DTO).

    Returns:
        Envelope ready to be returned from a FastAPI route.

    Example:
        >>> api_single("library", {"id": "lib_1", "name": "Movies"})
        {'type': 'library', 'data': {'id': 'lib_1', 'name': 'Movies'}}
    """
    return {"type": resource_type, "data": data}


def api_list(
    data: list[Any],
    pagination: Pagination | None = None,
    filters_applied: dict[str, Any] | None = None,
    metadata_extras: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Wrap a collection payload in the standard envelope.

    ``metadata`` is only emitted when at least one of the optional
    inputs is present, so minimal list responses stay tidy.

    Args:
        data: Already-serialized items (list of dicts).
        pagination: Cursor pagination descriptor, if applicable.
        filters_applied: Filters reflected in the result set.
        metadata_extras: Additional stable metadata (e.g. ``total_count``
            when a caller requests it outside the pagination envelope).

    Returns:
        Envelope ready to be returned from a FastAPI route.

    Example:
        >>> api_list([{"id": "mov_1"}], Pagination(has_more=False))
        {'type': 'list', 'data': [{'id': 'mov_1'}], 'metadata': {'pagination': {'has_more': False}}}
    """
    response: dict[str, Any] = {"type": "list", "data": data}
    metadata: dict[str, Any] = {}
    if pagination is not None:
        metadata["pagination"] = pagination.to_dict()
    if filters_applied:
        metadata["filters_applied"] = filters_applied
    if metadata_extras:
        metadata.update(metadata_extras)
    if metadata:
        response["metadata"] = metadata
    return response


__all__ = [
    "Pagination",
    "api_list",
    "api_single",
]
