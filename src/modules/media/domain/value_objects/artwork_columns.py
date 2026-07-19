"""The trio of top-level artwork references for a title (ADR-029).

Poster / backdrop / logo travel together everywhere the mirror flows —
the repository projection, the job's per-field result, and the update
signature. Bundling them into one value object replaces a three-argument
data clump (and a stringly-keyed ``dict``) with a single typed value,
and gives later phases (season posters, stills) one place to grow.

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
        poster: Poster reference, or ``None``.
        backdrop: Backdrop reference, or ``None``.
        logo: Title-logo reference, or ``None``.

    Example:
        >>> cols = ArtworkColumns(poster=ImageUrl("/api/v1/artwork/ab.jpg"))
        >>> cols.poster.is_remote
        False
    """

    poster: ImageUrl | None = None
    backdrop: ImageUrl | None = None
    logo: ImageUrl | None = None


__all__ = ["ArtworkColumns"]
