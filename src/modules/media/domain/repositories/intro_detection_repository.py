"""Intro-detection role interface (ADR-033).

The narrow contract the season-scoped intro-detection job and the manual
intro-edit use cases depend on: the eligibility queue, the per-season job
state transition, and the per-episode marker writes — all direct table
updates that avoid round-tripping the ``Series`` aggregate. Carved out of
the series catalog god-repository; migrates with the intro subdomain
(ADR-032). Intro detection is series-only (movies have no intro markers).
"""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from datetime import datetime

from src.modules.media.domain.entities.season import Season
from src.modules.media.domain.value_objects import (
    EpisodeId,
    IntroDetectionState,
    IntroMarker,
    SeasonId,
)


class SeriesIntroDetectionRepository(ABC):
    """Intro-detection operations over ``seasons`` / ``episodes``."""

    @abstractmethod
    async def find_seasons_pending_intro_detection(
        self,
        limit: int,
        *,
        stale_before: datetime,
    ) -> Sequence[Season]:
        """Return seasons whose intro-detection job has not converged yet.

        A season is eligible when it is:

        * ``NOT_STARTED`` — never attempted; or
        * ``INSUFFICIENT_EPISODES`` *and* its current (non-deleted)
          episode count exceeds ``intro_detection_attempted_episode_count``
          — i.e. new episodes landed since the last attempt, so the
          outcome could now differ. A season whose episode set hasn't
          grown is NOT retried, so a permanently-small season (e.g. a
          2-part miniseries) stops monopolising the queue; or
        * ``IN_PROGRESS`` with ``intro_detection_attempted_at`` older than
          ``stale_before`` — an orphaned claim (the worker died
          mid-detection), reclaimed so it self-heals.

        ``COMPLETED``, ``FAILED``, and ``DISABLED`` are excluded;
        ``FAILED`` and ``DISABLED`` require an explicit operator reset.

        Ordered by ``intro_detection_attempted_at`` ascending with NULLs
        first, then ``id``, so never-attempted seasons run before any
        already-attempted one.

        Returned ``Season`` entities have their ``episodes`` collection
        eagerly loaded (with file variants) so the detection job can
        iterate file paths without N+1 queries. Soft-deleted seasons
        and episodes are filtered out.

        Args:
            limit: Maximum number of seasons to return.
            stale_before: Cutoff for reclaiming orphaned ``IN_PROGRESS``
                seasons — those last attempted before this instant are
                considered abandoned and made eligible again.

        Returns:
            Sequence of seasons eligible for the next detection tick.
        """
        ...

    @abstractmethod
    async def find_season_for_intro_detection(self, season_id: SeasonId) -> Season | None:
        """Load a single season ready to be handed to the detector.

        Same shape as one row of
        :meth:`find_seasons_pending_intro_detection` (episodes and their
        file variants eagerly loaded, soft-deleted rows filtered out) but
        addressed by id and with no eligibility filter: the operator-
        triggered "detect now" path decides for itself whether the
        season should run, so a ``COMPLETED`` or ``FAILED`` season is
        still returned here.

        Args:
            season_id: External id of the season (ssn_xxx).

        Returns:
            The season with its episodes loaded, or ``None`` when no live
            season with that id exists.
        """
        ...

    @abstractmethod
    async def update_season_intro_detection(
        self,
        season_id: SeasonId,
        state: IntroDetectionState,
        *,
        attempted_at: datetime | None = None,
        attempted_episode_count: int | None = None,
        error: str | None = None,
    ) -> bool:
        """Persist intro-detection job state for a season.

        Direct UPDATE on the ``seasons`` table so the detection job can
        record progress and outcomes without round-tripping the parent
        ``Series`` aggregate per season. Domain-side state machine
        validation belongs on the ``Season`` entity; callers are expected
        to drive transitions via ``with_detection_started`` etc. and pass
        the resulting state here.

        Args:
            season_id: External id of the season (ssn_xxx).
            state: New ``IntroDetectionState`` value.
            attempted_at: When the job ran. Pass ``None`` to leave the
                column unchanged for transient transitions like
                ``IN_PROGRESS``.
            attempted_episode_count: Episode count observed this attempt,
                used to decide whether an ``INSUFFICIENT_EPISODES`` season
                is worth retrying later. Pass ``None`` to leave it
                unchanged (e.g. on the ``IN_PROGRESS`` claim).
            error: Diagnostic message for ``FAILED`` runs, or ``None`` to
                clear.

        Returns:
            ``True`` if a row was updated, ``False`` if no season with
            that id exists.
        """
        ...

    @abstractmethod
    async def update_episode_intro(
        self,
        episode_id: EpisodeId,
        marker: IntroMarker | None,
    ) -> bool:
        """Persist (or clear) the intro marker for a single episode.

        Direct UPDATE on the ``episodes`` table covering all five intro
        columns at once. The detection job calls this per-episode after
        cross-correlation; the manual-edit endpoint also uses it to set
        a ``MANUAL`` marker without rewriting the entire ``Series``
        aggregate.

        Args:
            episode_id: External id of the episode (epi_xxx).
            marker: The marker to persist, or ``None`` to clear all five
                intro columns.

        Returns:
            ``True`` if a row was updated, ``False`` if no episode with
            that id exists.
        """
        ...

    @abstractmethod
    async def clear_auto_intro_markers_for_season(self, season_id: SeasonId) -> int:
        """Clear AUTO_DETECTED intro markers on a season's episodes.

        Bulk UPDATE that nulls the five intro columns for every episode
        of the season whose marker source is ``AUTO_DETECTED``. MANUAL
        markers are left untouched. Used by the re-detect flow so a
        re-run starts from a clean slate without dropping operator edits.

        Args:
            season_id: External id of the season (ssn_xxx).

        Returns:
            The number of episode rows cleared.
        """
        ...


__all__ = ["SeriesIntroDetectionRepository"]
