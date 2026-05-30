"""Scheduled / manual catalog-wide dedup sweep (ADR-015 Phase 6.5)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from src.modules.media.application.dtos.conflict_dtos import (
    DetectMovieConflictsInput,
    SweepMovieConflictsOutput,
)

if TYPE_CHECKING:
    from src.modules.media.application.unit_of_work import MediaUnitOfWorkFactory
    from src.modules.media.application.use_cases.detect_movie_conflicts import (
        DetectMovieConflictsUseCase,
    )

_logger = logging.getLogger(__name__)


class SweepMovieConflictsUseCase:
    """Walk every movie in the catalog and run the conflict detector.

    Event-driven detection (``OnMediaEnrichedHandler``) only fires when
    a movie is freshly enriched. That misses two real-world cases:

    - A duplicate that was already in the catalog when the *first* copy
      was enriched (the second copy comes in later and is never
      re-enriched, so no event ever reaches the detector).
    - A pair where neither side ever locked a TMDB id; the title+year
      fallback (ADR-015 Phase 4) is the only thing that can catch them,
      but it too only runs from the enrich handler.

    This sweep is the periodic re-check: snapshot the catalog, then
    invoke :class:`DetectMovieConflictsUseCase` once per movie. Each
    detector run opens its own UoW so a single failing pair never aborts
    the whole pass. The sweep itself never re-enriches anyone — it only
    re-evaluates the existing catalog state.

    Args:
        uow_factory: Used to take a cheap snapshot of every movie id
            (and its tmdb_id) at the start of the sweep. The detector
            re-opens its own UoW per movie.
        detect_use_case: The per-movie detector. Receives the optional
            ``tmdb_id`` (``None`` for un-enriched entries → fallback
            pass only).
    """

    def __init__(
        self,
        uow_factory: MediaUnitOfWorkFactory,
        detect_use_case: DetectMovieConflictsUseCase,
    ) -> None:
        self._uow_factory = uow_factory
        self._detect_use_case = detect_use_case

    async def execute(self) -> SweepMovieConflictsOutput:
        """Run a single sweep pass and return the aggregate counters."""
        async with self._uow_factory() as uow:
            movies = list(await uow.movies.list_all())

        snapshot = [(str(m.id), m.tmdb_id.value if m.tmdb_id else None) for m in movies]

        created_ids: list[str] = []
        for media_id, tmdb_id in snapshot:
            try:
                result = await self._detect_use_case.execute(
                    DetectMovieConflictsInput(media_id=media_id, tmdb_id=tmdb_id),
                )
            except Exception:
                # Best-effort: a single bad row must not abort the
                # whole sweep. Detector already logs the per-pair
                # context internally; here we just keep going.
                _logger.exception(
                    "[scan-dedup-sweep] detect failed for movie %s; continuing",
                    media_id,
                )
                continue
            created_ids.extend(result.conflict_ids)

        _logger.info(
            "[scan-dedup-sweep] pass complete",
            extra={
                "movies_scanned": len(snapshot),
                "conflicts_created": len(created_ids),
            },
        )
        return SweepMovieConflictsOutput(
            movies_scanned=len(snapshot),
            conflicts_created=len(created_ids),
            conflict_ids=created_ids,
        )


__all__ = ["SweepMovieConflictsUseCase"]
