"""The mirrorable artwork references of a title (ADR-029).

The image references a title exposes travel together everywhere the
mirror flows — the repository projection, the job's per-field result,
and the update signature. Bundling them into one value object replaces a
data clump (and a stringly-keyed ``dict``) with a single typed value.

Each kind populates the subset that applies to it: movies and series set
``poster`` / ``backdrop`` / ``logo``; a season sets ``poster``; an
episode sets ``still``. Unused references stay ``None`` and the mirror
skips them.

Each reference is an :class:`ImageUrl` — dual-mode, so it carries either
a remote provider URL or a local ``/api/v1/artwork/...`` path — which
keeps the ``is_remote`` decision on the value object rather than on
loose strings.
"""

from src.building_blocks.domain.value_objects import CompoundValueObject
from src.shared_kernel.value_objects.image_url import ImageUrl


class ArtworkColumns(CompoundValueObject):
    """Poster / backdrop / logo references for one title.

    Attributes:
        poster: Poster reference (movie / series / season), or ``None``.
        backdrop: Backdrop reference (movie / series), or ``None``.
        logo: Title-logo reference (movie / series), or ``None``.
        still: Episode still reference, or ``None``.

    Example:
        >>> cols = ArtworkColumns(poster=ImageUrl("/api/v1/artwork/ab.jpg"))
        >>> cols.poster.is_remote
        False
    """

    poster: ImageUrl | None = None
    backdrop: ImageUrl | None = None
    logo: ImageUrl | None = None
    still: ImageUrl | None = None


__all__ = ["ArtworkColumns"]
