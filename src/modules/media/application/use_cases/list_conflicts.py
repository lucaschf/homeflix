"""Admin-side conflict queue listing (ADR-015 Phase 1)."""

from src.modules.media.application.dtos.conflict_dtos import (
    ConflictCandidateSummary,
    ConflictSummary,
    ListConflictsInput,
    ListConflictsOutput,
)
from src.modules.media.application.unit_of_work import MediaUnitOfWorkFactory
from src.modules.media.domain.entities.media_conflict import MediaConflict
from src.modules.media.domain.entities.movie import Movie
from src.modules.media.domain.value_objects import MovieId


class ListConflictsUseCase:
    """List pending content-identity conflicts for the admin queue.

    Hydrates each conflict with title/year projections of both
    candidates so the UI doesn't have to make N follow-up calls.
    Phase 1 resolves ``"movie"`` candidates via the Movie repository;
    series candidates simply surface with ``title=None`` until the
    Series support lands.

    Args:
        uow_factory: Factory that opens a fresh media Unit of Work.
    """

    def __init__(self, uow_factory: MediaUnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def execute(self, input_dto: ListConflictsInput) -> ListConflictsOutput:
        """Return one page of pending conflicts, newest-first."""
        async with self._uow_factory() as uow:
            page = await uow.media_conflicts.list_pending(
                cursor=input_dto.cursor,
                limit=input_dto.limit,
            )
            if not page.items:
                return ListConflictsOutput(
                    items=[],
                    next_cursor=page.pagination.next_cursor,
                    has_more=page.pagination.has_more,
                )

            movie_ids = _collect_movie_ids(page.items)
            movies_by_id = await uow.movies.find_by_ids(movie_ids) if movie_ids else {}

            return ListConflictsOutput(
                items=[_build_summary(c, movies_by_id) for c in page.items],
                next_cursor=page.pagination.next_cursor,
                has_more=page.pagination.has_more,
            )


def _collect_movie_ids(conflicts: list[MediaConflict]) -> list[MovieId]:
    """Collect distinct movie ids referenced by either side of any conflict."""
    seen: set[str] = set()
    out: list[MovieId] = []
    for c in conflicts:
        for candidate_id, candidate_type in (
            (c.candidate_a_id, c.candidate_a_type),
            (c.candidate_b_id, c.candidate_b_type),
        ):
            if candidate_type != "movie" or candidate_id in seen:
                continue
            seen.add(candidate_id)
            out.append(MovieId(candidate_id))
    return out


def _build_summary(
    conflict: MediaConflict,
    movies_by_id: dict[str, Movie],
) -> ConflictSummary:
    """Project a ``MediaConflict`` + looked-up candidate movies into the DTO."""
    return ConflictSummary(
        conflict_id=str(conflict.id),
        candidate_a=_build_candidate(
            conflict.candidate_a_id,
            conflict.candidate_a_type,
            movies_by_id,
        ),
        candidate_b=_build_candidate(
            conflict.candidate_b_id,
            conflict.candidate_b_type,
            movies_by_id,
        ),
        match_reason=conflict.match_reason.value,
        runtime_delta_minutes=conflict.runtime_delta_minutes,
        suggested_action=conflict.suggested_action.value,
        detected_at=conflict.created_at,
    )


def _build_candidate(
    media_id: str,
    media_type: str,
    movies_by_id: dict[str, Movie],
) -> ConflictCandidateSummary:
    """Hydrate one side of the pair with the looked-up movie (when present)."""
    if media_type == "movie":
        movie = movies_by_id.get(media_id)
        if movie is not None:
            return ConflictCandidateSummary(
                media_id=media_id,
                media_type=media_type,
                title=movie.title.value,
                year=movie.year.value,
            )
    return ConflictCandidateSummary(
        media_id=media_id,
        media_type=media_type,
        title=None,
        year=None,
    )


__all__ = ["ListConflictsUseCase"]
