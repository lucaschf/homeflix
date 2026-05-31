"""Post-enrich conflict detector for Movie aggregates (ADR-015 Phases 1 + 3)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from src.modules.media.application.dtos.conflict_dtos import (
    DetectMovieConflictsInput,
    DetectMovieConflictsOutput,
)
from src.modules.media.domain.entities import MediaConflict
from src.modules.media.domain.entities.media_conflict import (
    MatchReason,
    ResolutionAction,
    ResolutionSource,
)
from src.modules.media.domain.events import (
    MediaConflictDetectedEvent,
    MovieMergedEvent,
)
from src.modules.media.domain.value_objects import MovieId

if TYPE_CHECKING:
    from src.building_blocks.application.event_bus import EventBus
    from src.modules.media.application.ports.library_health_port import (
        LibraryHealthPort,
    )
    from src.modules.media.application.unit_of_work import MediaUnitOfWorkFactory
    from src.modules.media.domain.entities.movie import Movie
    from src.modules.settings.domain.value_objects import ScanDedupConfig
    from src.modules.settings.infrastructure.runtime_settings import RuntimeSettings

_logger = logging.getLogger(__name__)


class DetectMovieConflictsUseCase:
    """Materialise (or silently absorb) content-identity collisions.

    Triggered by the post-enrich event handler (``MediaEnrichedEvent``).
    Looks up every other non-deleted movie sharing the same TMDB id and
    decides per-pair:

    - **Auto-merge silently** (ADR-015 Phase 3): when the existing
      candidate is orphaned (its file does not exist on disk **and**
      its library root is mounted), the freshly-enriched movie wins
      and the orphan is soft-deleted. A resolved-AUTO ``MediaConflict``
      row is persisted for audit and a ``MovieMergedEvent`` (with
      ``is_auto=True``) fans out to ``watch_progress`` + ``collections``.

    - **Queue for the admin** (ADR-015 Phase 1): otherwise a pending
      ``MediaConflict`` is created and a ``MediaConflictDetectedEvent``
      fires so the operator decides via the resolve endpoint.

    - **Skip**: when a blocking row already exists for the pair
      (pending or MARK_DISTINCT-resolved).

    Args:
        uow_factory: Factory that opens a fresh media Unit of Work.
        library_health: Port answering "is this file / library
            accessible right now?" — used to distinguish a real
            orphan ("operator moved the file elsewhere") from a
            transient I/O failure ("the drive is unmounted right
            now"). ``None`` disables the auto-merge branch entirely
            and every collision goes to the queue.
        event_bus: Optional event bus. When ``None`` no events are
            published — handy for unit tests.
        runtime_settings: Optional ``scan_dedup`` runtime settings
            source (ADR-013). When provided, the runtime-delta
            thresholds that classify a pending conflict come from the
            persisted bucket; ``None`` keeps the ADR-015 class-level
            defaults.
    """

    def __init__(
        self,
        uow_factory: MediaUnitOfWorkFactory,
        library_health: LibraryHealthPort | None = None,
        event_bus: EventBus | None = None,
        runtime_settings: RuntimeSettings | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._library_health = library_health
        self._event_bus = event_bus
        self._runtime_settings = runtime_settings

    async def execute(
        self,
        input_dto: DetectMovieConflictsInput,
    ) -> DetectMovieConflictsOutput:
        """Run the detector for one enriched movie."""
        created_ids: list[str] = []
        detected_events: list[MediaConflictDetectedEvent] = []
        merged_events: list[MovieMergedEvent] = []

        config = await self._scan_config()
        abs_threshold = None if config is None else config.runtime_delta_abs_minutes
        relative_threshold = None if config is None else config.runtime_delta_relative
        # Fallback is opt-out via settings, but stays off entirely when
        # no runtime-settings source is wired (e.g. unit tests).
        fallback_enabled = config is not None and config.title_year_fallback_enabled

        async with self._uow_factory() as uow:
            if input_dto.tmdb_id is None:
                # Sweep path (ADR-015 Phase 6.5): the movie carries no
                # TMDB id, so there is no strong pass to run. We only
                # need the self entity for the fallback comparison.
                self_movie = await uow.movies.find_by_id(MovieId(input_dto.media_id))
                others: list[Movie] = []
            else:
                candidates = await uow.movies.find_all_by_tmdb_id(input_dto.tmdb_id)
                self_movie = next(
                    (m for m in candidates if str(m.id) == input_dto.media_id),
                    None,
                )
                others = [m for m in candidates if str(m.id) != input_dto.media_id]

            if self_movie is None:
                # Defensive: detector fired but the movie vanished
                # between commit and handler dispatch.
                _logger.warning(
                    "Movie %s not found during conflict detection",
                    input_dto.media_id,
                )
                return DetectMovieConflictsOutput(conflicts_created=0, conflict_ids=[])

            self_runtime = _runtime_minutes(self_movie)
            handled_ids = {input_dto.media_id}

            # --- Strong pass: TMDB-id collisions (auto-merge eligible). ---
            for other in others:
                handled_ids.add(str(other.id))
                blocker = await uow.media_conflicts.find_blocking_pair(
                    input_dto.media_id,
                    str(other.id),
                )
                if blocker is not None:
                    # Either pending (no need to re-queue) or
                    # MARK_DISTINCT-resolved (operator already said
                    # the pair is intentionally distinct).
                    continue

                if await self._is_orphan(other):
                    persisted, merged_event = await self._auto_merge_orphan(
                        uow=uow,
                        self_movie=self_movie,
                        self_runtime=self_runtime,
                        orphan=other,
                    )
                    created_ids.append(str(persisted.id))
                    merged_events.append(merged_event)
                    continue

                persisted, detected = await self._queue_conflict(
                    uow=uow,
                    self_id=input_dto.media_id,
                    self_runtime=self_runtime,
                    other=other,
                    match_reason=MatchReason.TMDB_ID,
                    abs_threshold=abs_threshold,
                    relative_threshold=relative_threshold,
                )
                created_ids.append(str(persisted.id))
                detected_events.append(detected)

            # --- Fallback pass: (normalized_original_title, year). ---
            # Catches catalog entries whose enrichment never locked a
            # TMDB id. Weaker identity → always queue, never auto-merge.
            if fallback_enabled:
                fallback_matches = await self._collect_title_year_matches(
                    uow, self_movie, exclude=handled_ids
                )
                for other in fallback_matches:
                    blocker = await uow.media_conflicts.find_blocking_pair(
                        input_dto.media_id,
                        str(other.id),
                    )
                    if blocker is not None:
                        continue
                    persisted, detected = await self._queue_conflict(
                        uow=uow,
                        self_id=input_dto.media_id,
                        self_runtime=self_runtime,
                        other=other,
                        match_reason=MatchReason.TITLE_YEAR_FALLBACK,
                        abs_threshold=abs_threshold,
                        relative_threshold=relative_threshold,
                    )
                    created_ids.append(str(persisted.id))
                    detected_events.append(detected)

        # Publish outside the UoW so a slow subscriber doesn't hold
        # the write transaction open. Auto-merge events fan out to
        # cross-BC handlers (watch_progress + collections); detect
        # events feed audit / notifications.
        if self._event_bus is not None:
            for event in (*detected_events, *merged_events):
                await self._event_bus.publish(event)

        return DetectMovieConflictsOutput(
            conflicts_created=len(created_ids),
            conflict_ids=created_ids,
        )

    async def _scan_config(self) -> ScanDedupConfig | None:
        """Read the ``scan_dedup`` bucket, or ``None`` when not wired.

        ``None`` makes the detector fall back to the ADR-015 class
        defaults for the thresholds and disables the title+year
        fallback pass entirely (the unit-test path).
        """
        if self._runtime_settings is None:
            return None
        return await self._runtime_settings.scan_dedup()

    async def _queue_conflict(
        self,
        *,
        uow: object,
        self_id: str,
        self_runtime: float | None,
        other: Movie,
        match_reason: MatchReason,
        abs_threshold: float | None,
        relative_threshold: float | None,
    ) -> tuple[MediaConflict, MediaConflictDetectedEvent]:
        """Persist a pending conflict for the pair and build its event."""
        conflict = MediaConflict.detect(
            candidate_a_id=self_id,
            candidate_a_type="movie",
            candidate_a_runtime_minutes=self_runtime,
            candidate_b_id=str(other.id),
            candidate_b_type="movie",
            candidate_b_runtime_minutes=_runtime_minutes(other),
            match_reason=match_reason,
            abs_threshold_minutes=abs_threshold,
            relative_threshold=relative_threshold,
        )
        persisted = await uow.media_conflicts.save(conflict)  # type: ignore[attr-defined]
        event = MediaConflictDetectedEvent(
            conflict_id=str(persisted.id),
            candidate_a_id=persisted.candidate_a_id,
            candidate_b_id=persisted.candidate_b_id,
            match_reason=persisted.match_reason.value,
            suggested_action=persisted.suggested_action.value,
        )
        return persisted, event

    async def _collect_title_year_matches(
        self,
        uow: object,
        self_movie: Movie,
        *,
        exclude: set[str],
    ) -> list[Movie]:
        """Find same-year movies whose normalized title matches ``self_movie``.

        Compares on ``original_title`` (falling back to ``title``) using
        the deterministic :attr:`Title.normalized` key, so casing /
        accent differences still match. Ids in ``exclude`` (self + the
        TMDB pass) are skipped to avoid double-queuing.
        """
        self_key = _normalized_identity_title(self_movie)
        candidates = await uow.movies.find_all_by_year(self_movie.year.value)  # type: ignore[attr-defined]
        return [
            m
            for m in candidates
            if str(m.id) not in exclude and _normalized_identity_title(m) == self_key
        ]

    async def _is_orphan(self, movie: Movie) -> bool:
        """``True`` when every file of ``movie`` is missing and the library is healthy.

        ``False`` when:
        - The library health port is not wired (Phase 1 fallback).
        - Any of the movie's files still exists on disk.
        - The library root itself is inaccessible (transient I/O —
          we cannot trust the file-missing signal).
        """
        if self._library_health is None:
            return False
        for file in movie.files:
            if await self._library_health.is_file_accessible(file.file_path.value):
                return False
        return await self._library_health.is_library_root_accessible(movie.library_id)

    async def _auto_merge_orphan(
        self,
        *,
        uow: object,
        self_movie: Movie,
        self_runtime: float | None,
        orphan: Movie,
    ) -> tuple[MediaConflict, MovieMergedEvent]:
        """Persist a resolved-AUTO conflict and soft-delete the orphan."""
        # ``uow`` is typed ``object`` here because importing
        # MediaUnitOfWork would form a runtime cycle through this
        # module — the caller passes the live UoW from the same
        # ``async with`` block above.
        conflict = MediaConflict.detect(
            candidate_a_id=str(self_movie.id),
            candidate_a_type="movie",
            candidate_a_runtime_minutes=self_runtime,
            candidate_b_id=str(orphan.id),
            candidate_b_type="movie",
            candidate_b_runtime_minutes=_runtime_minutes(orphan),
            match_reason=MatchReason.TMDB_ID,
        )
        resolved = conflict.resolve(
            ResolutionAction.MERGE_REPLACE,
            winner_id=str(self_movie.id),
            source=ResolutionSource.AUTO,
        )
        persisted = await uow.media_conflicts.save(resolved)  # type: ignore[attr-defined]

        loser_id = persisted.loser_id()
        if loser_id is None:  # pragma: no cover — guarded by aggregate
            raise RuntimeError("auto-merge resolved row missing loser_id")

        deleted = await uow.movies.delete(MovieId(loser_id))  # type: ignore[attr-defined]
        if not deleted:
            _logger.warning(
                "Orphan movie %s missing during auto-merge of %s",
                loser_id,
                persisted.id,
            )

        event = MovieMergedEvent(
            conflict_id=str(persisted.id),
            winner_id=str(self_movie.id),
            loser_id=loser_id,
            keep_loser_variants=False,
            is_auto=True,
        )
        _logger.info(
            "Auto-merged orphan %s into %s (conflict %s)",
            loser_id,
            self_movie.id,
            persisted.id,
        )
        return persisted, event


def _runtime_minutes(movie: Movie) -> float | None:
    """Convert ``Movie.duration`` (seconds) to minutes, or ``None`` when zero."""
    if movie.duration.value <= 0:
        return None
    return movie.duration.value / 60.0


def _normalized_identity_title(movie: Movie) -> str:
    """Comparison key for the title+year fallback (original title preferred)."""
    return (movie.original_title or movie.title).normalized


__all__ = ["DetectMovieConflictsUseCase"]
