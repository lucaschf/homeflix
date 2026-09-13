"""Port for asking the Media catalog about titles referenced by progress rows.

The Watch Progress BC decorates its "Continue Watching" output with
the title/poster of the referenced movie or series, and refuses to
record or reveal progress on a title the caller's profile cannot see.
This port is the only surface through which it reaches into the Media
catalog — the adapter lives in ``watch_progress.infrastructure.acl``.

Every method takes the caller's ``ViewingPolicy`` and applies it on both
axes. A title that does not exist and one the policy hides come back
the same way — absent — so nothing built on this port can tell them
apart (ADR-035).

See ADR-009 for the cross-BC read port pattern.
"""

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from src.shared_kernel.content_policy import ViewingPolicy
from src.shared_kernel.value_objects.media_id import MovieId, SeriesId


@dataclass(frozen=True)
class MovieDisplayInfo:
    """Minimal movie data the "continue watching" card needs.

    Attributes:
        media_id: External id (``mov_xxx``).
        title: Already-localized title.
        poster_path: Poster URL or ``None``.
        backdrop_path: Backdrop URL or ``None``.
    """

    media_id: str
    title: str
    poster_path: str | None
    backdrop_path: str | None


@dataclass(frozen=True)
class EpisodeInfo:
    """Minimal episode data needed to pick the next episode to resume.

    Attributes:
        season_number: One-based season number.
        episode_number: One-based episode number within the season.
        title: Episode title (not localized today — no translations
            exist for episode titles).
        duration_seconds: Canonical runtime in seconds.
    """

    season_number: int
    episode_number: int
    title: str
    duration_seconds: int


@dataclass(frozen=True)
class SeriesWithEpisodesInfo:
    """Series metadata with its episode list.

    The ``episodes`` sequence is already sorted by ``(season_number,
    episode_number)`` ascending so the selection logic can treat it as
    chronological progression without re-sorting.
    """

    series_id: str
    title: str
    poster_path: str | None
    backdrop_path: str | None
    episodes: Sequence[EpisodeInfo]


@dataclass(frozen=True)
class MediaDisplayBatch:
    """Display data for the titles a policy lets the caller see.

    Attributes:
        movies: Movie display data keyed by external id (``mov_xxx``).
        series: Series display data keyed by external id (``ser_xxx``).
    """

    movies: Mapping[str, MovieDisplayInfo]
    series: Mapping[str, SeriesWithEpisodesInfo]


class MediaLookupPort(ABC):
    """Resolve titles in batches, through the caller's viewing policy."""

    @abstractmethod
    async def find_visible_titles(
        self,
        *,
        movie_ids: Sequence[MovieId],
        series_ids: Sequence[SeriesId],
        policy: ViewingPolicy,
    ) -> frozenset[str]:
        """Answer which of these titles the policy lets the caller see.

        A series is the unit of restriction: an episode is visible
        exactly when its series is.

        Args:
            movie_ids: Movies to check.
            series_ids: Series to check.
            policy: The caller's viewing policy, applied on both axes.

        Returns:
            External ids (``mov_xxx`` / ``ser_xxx``) of the visible
            titles. A title that does not exist, is soft-deleted, or is
            denied by the policy is absent.
        """
        ...

    @abstractmethod
    async def find_display_info(
        self,
        *,
        movie_ids: Sequence[MovieId],
        series_ids: Sequence[SeriesId],
        lang: str,
        policy: ViewingPolicy,
    ) -> MediaDisplayBatch:
        """Load display data for the titles the policy lets the caller see.

        Args:
            movie_ids: Movies to load.
            series_ids: Series to load, each with its sorted episodes.
            lang: Language for the localized titles and artwork.
            policy: The caller's viewing policy, applied on both axes.

        Returns:
            Display data for the visible titles only; a title that does
            not exist or is denied by the policy has no entry.
        """
        ...


__all__ = [
    "EpisodeInfo",
    "MediaDisplayBatch",
    "MediaLookupPort",
    "MovieDisplayInfo",
    "SeriesWithEpisodesInfo",
]
