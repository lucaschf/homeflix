"""Credits-detection role interfaces (ADR-033).

The narrow contract the credits-detection job and the admin credits-status
listing depend on: pending-work queues, per-title state counters, the
status projection, and the direct marker/state update that avoids an
aggregate round-trip. Carved out of the movie/series catalog
god-repositories; migrates with the credits subdomain (ADR-032).
"""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass

from src.modules.media.domain.entities.episode import Episode
from src.modules.media.domain.entities.movie import Movie
from src.modules.media.domain.value_objects import (
    CreditsDetectionState,
    CreditsMarker,
    EpisodeId,
    MovieId,
)


@dataclass(frozen=True)
class CreditsStatusRow:
    """Lightweight projection of a title's credits-detection status.

    Used by the admin "credits status" listing so it can show every
    title's state + marker without loading entities and their file
    variants. Episode-only context (``series_id``/``season_number``/
    ``episode_number``) is ``None`` for movies; the admin UI uses it to
    deep-link into the per-episode editor.
    """

    media_id: str
    title: str
    state: str
    start_seconds: int | None
    source: str | None
    confidence: float | None
    series_id: str | None = None
    season_number: int | None = None
    episode_number: int | None = None


class MovieCreditsDetectionRepository(ABC):
    """Credits-detection operations over the ``movies`` table."""

    @abstractmethod
    async def count_credits_states(self) -> dict[str, int]:
        """Return ``{credits_detection_state: count}`` over non-deleted movies."""
        ...

    @abstractmethod
    async def list_credits_status(
        self, state: str | None, limit: int, offset: int
    ) -> tuple[Sequence[CreditsStatusRow], int]:
        """Return a page of movie credits-status rows + the total count.

        Args:
            state: Filter by ``credits_detection_state``, or ``None`` for all.
            limit: Page size.
            offset: Page offset.

        Returns:
            ``(rows, total)`` — newest-marker-first, then by title.
        """
        ...

    @abstractmethod
    async def find_pending_credits_detection(self, limit: int) -> Sequence[Movie]:
        """Return up to ``limit`` movies whose credits detection has not run.

        Filters for ``credits_detection_state == NOT_STARTED`` with
        file variants eager-loaded (the job needs ``primary_file``).
        Soft-deleted rows excluded; sorted ``id ASC`` for steady forward
        progress across ticks.
        """
        ...

    @abstractmethod
    async def update_movie_credits(
        self,
        movie_id: MovieId,
        marker: CreditsMarker | None,
        state: CreditsDetectionState,
    ) -> bool:
        """Persist the credits marker + detection state for one movie.

        Direct UPDATE of the four credits-marker columns plus
        ``credits_detection_state`` on the ``movies`` row. ``marker=None``
        clears the marker columns (IN_PROGRESS / NO_CREDITS_FOUND /
        FAILED / clear); a non-null marker writes the onset (COMPLETED /
        manual edit).

        Returns:
            ``True`` if a row was updated, ``False`` if no movie matched.
        """
        ...


class SeriesCreditsDetectionRepository(ABC):
    """Credits-detection operations over the ``episodes`` table."""

    @abstractmethod
    async def count_episode_credits_states(self) -> dict[str, int]:
        """Return ``{credits_detection_state: count}`` over non-deleted episodes."""
        ...

    @abstractmethod
    async def list_episode_credits_status(
        self, state: str | None, limit: int, offset: int
    ) -> tuple[Sequence[CreditsStatusRow], int]:
        """Return a page of episode credits-status rows + the total count.

        Rows carry ``series_id``/``season_number``/``episode_number`` so the
        admin UI can deep-link into the per-episode editor. Newest-marker
        first, then by series + season + episode.
        """
        ...

    @abstractmethod
    async def find_episodes_pending_credits_detection(self, limit: int) -> Sequence[Episode]:
        """Return episodes whose credits detection has not run yet.

        Filters for episodes in ``NOT_STARTED`` credits-detection state
        (per-file, unlike the season-scoped intro detection), with their
        file variants eager-loaded so the job can read the primary file
        path without an N+1. Soft-deleted episodes are excluded.
        """
        ...

    @abstractmethod
    async def update_episode_credits(
        self,
        episode_id: EpisodeId,
        marker: CreditsMarker | None,
        state: CreditsDetectionState,
    ) -> bool:
        """Persist the credits marker + detection state for one episode.

        Direct UPDATE of the four credits-marker columns plus
        ``credits_detection_state`` on the ``episodes`` row, avoiding a
        round-trip through the ``Series`` aggregate. ``marker=None`` clears
        the marker columns (used for IN_PROGRESS / NO_CREDITS_FOUND /
        FAILED transitions and for clearing); a non-null marker writes the
        onset (used on COMPLETED and manual edits).

        Returns:
            ``True`` if a row was updated, ``False`` if no episode matched.
        """
        ...


__all__ = [
    "CreditsStatusRow",
    "MovieCreditsDetectionRepository",
    "SeriesCreditsDetectionRepository",
]
