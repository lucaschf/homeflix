"""ContinueWatchingSelector — which episode should the user resume?

This domain service encodes the selection rule for the
"Continue Watching" list:

1. If any episode is ``IN_PROGRESS``, pick the highest-numbered one
   (treating ``(season, episode)`` as a lexicographic key).
2. Otherwise, if there are completed episodes, pick the first
   unwatched episode that follows the last completed one.
3. Otherwise, skip the series.

Kept pure so the application layer composes it without mocks — the
inputs are already-materialized ``EpisodeCandidate`` values.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.modules.watch_progress.domain.value_objects.watch_status import WatchStatus

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime

    from src.modules.watch_progress.domain.value_objects.episode_candidate import (
        EpisodeCandidate,
    )


@dataclass(frozen=True)
class ContinueWatchingSelection:
    """Outcome of running the selector over a series' candidates.

    Attributes:
        candidate: The episode to resume, or ``None`` when the series
            should be skipped (no in-progress episode, no unwatched
            episode after a completed one).
        latest_watched_at: Most recent ``last_watched_at`` across all
            candidates that had progress — the use case uses it as a
            display fallback for the "Continue Watching" card when the
            chosen candidate itself has no progress yet.
    """

    candidate: EpisodeCandidate | None
    latest_watched_at: datetime | None


class ContinueWatchingSelector:
    """Pick the episode to surface on the "Continue Watching" card."""

    def pick(self, candidates: Sequence[EpisodeCandidate]) -> ContinueWatchingSelection:
        """Apply the in-progress-then-next-unwatched rule.

        Args:
            candidates: Episodes ordered by ``(season, episode)``.

        Returns:
            A ``ContinueWatchingSelection`` describing the chosen
            candidate (if any) and the latest watched timestamp.
        """
        best_in_progress: EpisodeCandidate | None = None
        last_completed_idx: int | None = None
        latest_watched_at: datetime | None = None

        for idx, ep in enumerate(candidates):
            if ep.progress is None:
                continue
            if latest_watched_at is None or ep.progress.last_watched_at > latest_watched_at:
                latest_watched_at = ep.progress.last_watched_at

            if ep.progress.status == WatchStatus.IN_PROGRESS:
                best_in_progress = self._pick_later(best_in_progress, ep)
            elif ep.progress.status == WatchStatus.COMPLETED:
                last_completed_idx = max(
                    last_completed_idx if last_completed_idx is not None else -1, idx
                )

        if best_in_progress is not None:
            return ContinueWatchingSelection(
                candidate=best_in_progress,
                latest_watched_at=latest_watched_at,
            )

        if last_completed_idx is not None:
            for ep in candidates[last_completed_idx + 1 :]:
                if ep.progress is None:
                    return ContinueWatchingSelection(
                        candidate=ep,
                        latest_watched_at=latest_watched_at,
                    )

        return ContinueWatchingSelection(
            candidate=None,
            latest_watched_at=latest_watched_at,
        )

    @staticmethod
    def _pick_later(
        current_best: EpisodeCandidate | None,
        contender: EpisodeCandidate,
    ) -> EpisodeCandidate:
        """Return whichever candidate has the higher ``(season, episode)`` key."""
        if current_best is None:
            return contender
        contender_coords = (contender.season_number, contender.episode_number)
        current_coords = (current_best.season_number, current_best.episode_number)
        return contender if contender_coords > current_coords else current_best


__all__ = ["ContinueWatchingSelection", "ContinueWatchingSelector"]
