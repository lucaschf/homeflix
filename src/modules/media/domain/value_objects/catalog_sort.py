"""Sort order for the catalog by-genre listing."""

from enum import StrEnum


class CatalogSort(StrEnum):
    """Ordering options for ``GET /api/v1/catalog/by-genre/{genre}``.

    Part of the repository port vocabulary: the sort choice reaches
    ``MovieRepository.list_paginated_by_genre`` /
    ``SeriesRepository.list_paginated_by_genre`` because it drives the
    SQL ``ORDER BY`` and the cursor shape, so it belongs in the domain
    alongside the ports rather than in the application layer. Uses
    ``StrEnum`` (like :class:`~src.shared_kernel.value_objects.MediaType`)
    so the value serializes directly as a query-string / cursor token.

    Every order ultimately falls back to the internal autoincrement
    ``id`` as its final tie-breaker; without it the merged movie+series
    stream would be unstable and cursor pagination could duplicate or
    skip rows.

    Members:
        TITLE_ASC: ``LOWER(localized title)`` A→Z. The default — keeps
            the pre-sort behavior of the endpoint.
        TITLE_DESC: ``LOWER(localized title)`` Z→A.
        YEAR_DESC: Release year (movie ``year`` / series ``start_year``)
            newest first.
        YEAR_ASC: Release year oldest first.
        RECENTLY_ADDED: Insertion order, newest first (by ``created_at``
            across the merge, ``id DESC`` within each stream).

    Example:
        >>> CatalogSort.TITLE_ASC.value
        'title_asc'
        >>> CatalogSort("year_desc")
        <CatalogSort.YEAR_DESC: 'year_desc'>
    """

    TITLE_ASC = "title_asc"
    TITLE_DESC = "title_desc"
    YEAR_DESC = "year_desc"
    YEAR_ASC = "year_asc"
    RECENTLY_ADDED = "recently_added"


__all__ = ["CatalogSort"]
