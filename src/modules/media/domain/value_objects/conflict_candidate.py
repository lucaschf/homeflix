"""ConflictCandidate value object — one side of a media-conflict pair."""

from src.building_blocks.domain.value_objects import CompoundValueObject
from src.shared_kernel.value_objects.media_type import MediaType


class ConflictCandidate(CompoundValueObject):
    """One side of a detected duplicate-identity collision.

    Bundles the external id with its media-type discriminator so the
    pair always travels together. Replaces the loose
    ``(candidate_x_id: str, candidate_x_type: MediaType)`` data clump
    that previously rode through :class:`MediaConflict`'s fields and
    ``detect()``'s parameter list.

    Attributes:
        id: External id of the candidate (e.g. ``mov_xxx``).
        type: ``MediaType.MOVIE`` (Phase 1) or ``MediaType.SERIES``
            (later phase).

    Example:
        >>> ConflictCandidate(id="mov_2xK9mPqR7nL4", type=MediaType.MOVIE)
        ConflictCandidate(id='mov_2xK9mPqR7nL4', type=<MediaType.MOVIE: 'movie'>)
    """

    id: str
    type: MediaType


__all__ = ["ConflictCandidate"]
