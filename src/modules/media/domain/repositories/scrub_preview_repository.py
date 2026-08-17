"""Scrub-preview role interfaces (ADR-033).

The narrow contract the scrub-preview backfill job depends on: the
throttled "missing preview" queue and, for episodes, the direct
scrub-path write that marks an item processed without round-tripping the
``Series`` aggregate. Carved out of the movie/series catalog
god-repositories; migrates with the scrub-preview subdomain (ADR-032).

Movies have no dedicated scrub-path update — the job persists the path
through the aggregate ``save`` on the lean catalog repository — so the
movie role is read-only here.
"""

from abc import ABC, abstractmethod
from collections.abc import Sequence

from src.modules.media.domain.entities.episode import Episode
from src.modules.media.domain.entities.movie import Movie
from src.modules.media.domain.value_objects import EpisodeId


class MovieScrubPreviewRepository(ABC):
    """Scrub-preview read queue over the ``movies`` table."""

    @abstractmethod
    async def find_missing_scrub_preview(self, limit: int) -> Sequence[Movie]:
        """Return up to ``limit`` movies that have no scrub-preview thumbnails yet.

        Used by the periodic backfill job to throttle work — every tick
        picks at most ``limit`` movies and generates their sprites,
        which keeps CPU bounded on large catalogs. Soft-deleted rows
        are excluded; movies without a primary file are included so the
        caller can decide to skip them.
        """
        ...


class SeriesScrubPreviewRepository(ABC):
    """Scrub-preview read queue + direct path write over the ``episodes`` table."""

    @abstractmethod
    async def find_episodes_missing_scrub_preview(self, limit: int) -> Sequence[Episode]:
        """Return up to ``limit`` episodes that have no scrub-preview thumbnails yet.

        Returned ``Episode`` aggregates are detached from their parent
        ``Series``; the backfill job only needs the file path and id to
        do its work and this avoids loading a full series hierarchy per
        episode. Soft-deleted episodes are excluded.
        """
        ...

    @abstractmethod
    async def update_episode_scrub_preview_path(
        self,
        episode_id: EpisodeId,
        path: str | None,
    ) -> bool:
        """Persist the scrub-preview path for a single episode.

        Provided alongside ``find_episodes_missing_scrub_preview`` so
        the backfill job can mark items processed without round-tripping
        the entire ``Series`` aggregate — that round-trip would dominate
        runtime on series with many episodes.

        Args:
            episode_id: External id of the episode to update.
            path: Absolute path to the sprite VTT, or ``None`` to clear.

        Returns:
            ``True`` if a row was updated, ``False`` if no episode with
            that id exists.
        """
        ...


__all__ = ["MovieScrubPreviewRepository", "SeriesScrubPreviewRepository"]
