"""Which catalog title a collection entry names, and whether a policy reaches it.

Watchlist entries and custom-list items reference a whole title — a
movie or a series. Saving one is refused when the caller's profile
cannot see that title (ADR-035). These helpers are the single place the
write use cases turn a :class:`CollectionMediaId` into that title, ask
the catalog about it and build the refusal, so the watchlist toggle and
the custom-list add cannot disagree on which title is gated or on how a
refusal looks.
"""

from src.building_blocks.application.errors import ResourceNotFoundException
from src.modules.collections.application.ports import MediaLookupPort
from src.modules.collections.domain.value_objects import CollectionMediaId
from src.shared_kernel.content_policy import ViewingPolicy
from src.shared_kernel.value_objects.media_id import MovieId, SeriesId


def title_of(media_id: CollectionMediaId) -> MovieId | SeriesId:
    """Return the catalog title a collection media id names.

    The type comes from the id's own prefix, never from a caller-supplied
    media type, so a body that labels a series as a movie still gates —
    and refuses — the series.

    Args:
        media_id: A movie or series id.

    Returns:
        The id typed as a :class:`MovieId` or a :class:`SeriesId`.

    Example:
        >>> title_of(CollectionMediaId("ser_3yL8nQsT9mK5")).value
        'ser_3yL8nQsT9mK5'
    """
    return media_id.as_movie_id() if media_id.is_movie else media_id.as_series_id()


async def is_title_visible(
    media_lookup: MediaLookupPort,
    title: MovieId | SeriesId,
    policy: ViewingPolicy,
) -> bool:
    """Whether the policy lets the caller see one title.

    A deny-all policy answers ``False`` without reaching the catalog.

    Args:
        media_lookup: Port into the Media catalog.
        title: The movie or series to check.
        policy: The caller's viewing policy.

    Returns:
        ``True`` only when the title exists and the policy permits it.
    """
    if policy.denies_everything:
        return False
    if isinstance(title, MovieId):
        visible = await media_lookup.find_visible_titles(
            movie_ids=[title], series_ids=[], policy=policy
        )
    else:
        visible = await media_lookup.find_visible_titles(
            movie_ids=[], series_ids=[title], policy=policy
        )
    return title.value in visible


def title_not_found(title: MovieId | SeriesId) -> ResourceNotFoundException:
    """Build the 404 for a title the caller cannot save.

    The same exception is raised whether the title does not exist or the
    policy hides it, so the response cannot tell the two apart.

    Args:
        title: The movie or series that was refused.

    Returns:
        A ``ResourceNotFoundException`` naming the title.
    """
    resource_type = "Movie" if isinstance(title, MovieId) else "Series"
    return ResourceNotFoundException.for_resource(resource_type, title.value)


__all__ = ["is_title_visible", "title_not_found", "title_of"]
