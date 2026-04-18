"""Port for fetching display metadata of media referenced by progress rows.

The Watch Progress BC decorates its "Continue Watching" output with
the title/poster of the referenced movie or series. This port is the
only surface through which it reaches into the Media catalog — the
adapter lives in ``watch_progress.infrastructure.acl``.

See ADR-009 for the cross-BC read port pattern.
"""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass


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


class MediaLookupPort(ABC):
    """Fetch movie / series display data on demand.

    One call per item is fine for the "Continue Watching" list — it's
    capped at a handful of rows. Batching would only pay off if the
    home-page consumer ever grew past tens of items.
    """

    @abstractmethod
    async def get_movie(self, media_id: str, lang: str) -> MovieDisplayInfo | None:
        """Resolve a single movie. Returns ``None`` when id is unknown."""
        ...

    @abstractmethod
    async def get_series_with_episodes(
        self,
        series_id: str,
        lang: str,
    ) -> SeriesWithEpisodesInfo | None:
        """Resolve a series including the sorted episode list."""
        ...


__all__ = [
    "EpisodeInfo",
    "MediaLookupPort",
    "MovieDisplayInfo",
    "SeriesWithEpisodesInfo",
]
