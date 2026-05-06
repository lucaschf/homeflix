"""Collection value object — TMDB franchise/series a movie belongs to."""

from src.building_blocks.domain import CompoundValueObject


class Collection(CompoundValueObject):
    """A TMDB collection (franchise) a movie belongs to.

    Captures just enough metadata to render a "Part of <name> · N
    movies" pill on the detail page and link out to a future
    collection-browse view. ``parts_count`` reflects the size of the
    collection on TMDB at enrichment time, not how many of those
    titles exist in the local catalog.

    Attributes:
        tmdb_id: TMDB collection id (e.g. ``8091`` for Alien Collection).
        name: Display name (e.g. ``"Alien Collection"``).
        parts_count: Number of titles in the collection per TMDB.

    Example:
        >>> Collection(tmdb_id=8091, name="Alien Collection", parts_count=6)
    """

    tmdb_id: int
    name: str
    parts_count: int


__all__ = ["Collection"]
