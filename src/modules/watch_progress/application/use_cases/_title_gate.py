"""Which catalog title a progress row belongs to, and whether a policy reaches it.

A progress row is keyed by what was played — a movie, or one episode of
a series — but visibility is decided per *title*: a movie, or the whole
series (ADR-035, known limitations). These helpers are the single place
the use cases turn a :class:`WatchableMediaId` into that title and ask
the catalog about it, so the save, read and "Continue Watching" paths
cannot disagree on which id is gated.
"""

from collections.abc import Iterable

from src.building_blocks.application.errors import ResourceNotFoundException
from src.modules.watch_progress.application.ports import MediaLookupPort
from src.modules.watch_progress.domain.value_objects import WatchableMediaId
from src.shared_kernel.content_policy import ViewingPolicy
from src.shared_kernel.value_objects.media_id import MovieId, SeriesId


def title_of(media_id: WatchableMediaId) -> MovieId | SeriesId:
    """Return the catalog title a watchable id belongs to.

    The type comes from the id's own shape, never from a caller-supplied
    media type, so a body that labels an episode as a movie still gates
    the series.

    Args:
        media_id: A movie id or a composite episode id.

    Returns:
        The movie id itself, or the episode's parent series id.

    Example:
        >>> title_of(WatchableMediaId("epi_ser_3yL8nQsT9mK5_1_2")).value
        'ser_3yL8nQsT9mK5'
    """
    return media_id.as_movie_id() if media_id.is_movie else media_id.as_episode().series_id


async def find_visible_titles(
    media_lookup: MediaLookupPort,
    titles: Iterable[MovieId | SeriesId],
    policy: ViewingPolicy,
) -> frozenset[str]:
    """Ask the catalog, in one call, which of these titles the policy reaches.

    Args:
        media_lookup: Port into the Media catalog.
        titles: Movie and series ids, in any mix.
        policy: The caller's viewing policy.

    Returns:
        External ids of the visible titles; missing and hidden titles
        are both absent.
    """
    movie_ids: list[MovieId] = []
    series_ids: list[SeriesId] = []
    for title in titles:
        if isinstance(title, MovieId):
            movie_ids.append(title)
        else:
            series_ids.append(title)
    return await media_lookup.find_visible_titles(
        movie_ids=movie_ids,
        series_ids=series_ids,
        policy=policy,
    )


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
    return title.value in await find_visible_titles(media_lookup, [title], policy)


def title_not_found(title: MovieId | SeriesId) -> ResourceNotFoundException:
    """Build the 404 for a title the caller cannot see.

    The same exception is raised whether the title does not exist or the
    policy hides it, so the response cannot tell the two apart.

    Args:
        title: The movie or series that was refused.

    Returns:
        A ``ResourceNotFoundException`` naming the title.
    """
    resource_type = "Movie" if isinstance(title, MovieId) else "Series"
    return ResourceNotFoundException.for_resource(resource_type, title.value)


__all__ = ["find_visible_titles", "is_title_visible", "title_not_found", "title_of"]
