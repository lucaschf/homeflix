"""Admin-side conflict queue + audit listing (ADR-015 Phases 1 + 3)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.building_blocks.domain.errors import DomainValidationException
from src.modules.media.application.dtos.conflict_dtos import (
    ConflictCandidateFile,
    ConflictCandidateSummary,
    ConflictSummary,
    ListConflictsInput,
    ListConflictsOutput,
)
from src.modules.media.domain.entities.media_conflict import (
    MediaConflict,
    ResolutionSource,
)
from src.modules.media.domain.value_objects import MovieId
from src.shared_kernel.value_objects.media_type import MediaType

if TYPE_CHECKING:
    from src.modules.media.application.unit_of_work import MediaUnitOfWorkFactory
    from src.modules.media.domain.entities.movie import Movie
    from src.modules.media.domain.value_objects import MediaFile

_VALID_STATES = ("pending", "resolved")
_VALID_SOURCES = ("manual", "auto")


class ListConflictsUseCase:
    """List content-identity conflicts for the admin UI.

    Default state is ``pending`` (the operator queue). ``resolved``
    powers the audit view; it accepts an optional ``source`` filter
    so the UI can split admin actions from Phase 3 auto-merges.

    Hydrates each conflict with title/year projections of both
    candidates so the UI doesn't have to make N follow-up calls. The
    loser of a resolved-MERGE row is soft-deleted, so the repository
    returns ``None`` for its title — surfaced verbatim.

    Args:
        uow_factory: Factory that opens a fresh media Unit of Work.
    """

    def __init__(self, uow_factory: MediaUnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def execute(self, input_dto: ListConflictsInput) -> ListConflictsOutput:
        """Return one page of conflicts matching the ``state`` filter."""
        state = input_dto.state
        if state not in _VALID_STATES:
            raise DomainValidationException(
                message=f"Unknown state '{state}'; must be one of {_VALID_STATES}",
                message_code="MEDIA_CONFLICT_LIST_INVALID_STATE",
                object_type="MediaConflict",
            )

        source = _parse_source(input_dto.source)

        if state == "pending" and source is not None:
            # ``source`` only makes sense for resolved rows. Surface
            # the misuse instead of silently ignoring.
            raise DomainValidationException(
                message="source filter is only valid for state=resolved",
                message_code="MEDIA_CONFLICT_LIST_SOURCE_FOR_PENDING",
                object_type="MediaConflict",
            )

        async with self._uow_factory() as uow:
            if state == "pending":
                page = await uow.media_conflicts.list_pending(
                    cursor=input_dto.cursor,
                    limit=input_dto.limit,
                )
            else:
                page = await uow.media_conflicts.list_resolved(
                    source=source,
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


def _parse_source(raw: str | None) -> ResolutionSource | None:
    if raw is None:
        return None
    if raw not in _VALID_SOURCES:
        raise DomainValidationException(
            message=f"Unknown source '{raw}'; must be one of {_VALID_SOURCES}",
            message_code="MEDIA_CONFLICT_LIST_INVALID_SOURCE",
            object_type="MediaConflict",
        )
    return ResolutionSource(raw)


def _collect_movie_ids(conflicts: list[MediaConflict]) -> list[MovieId]:
    """Collect distinct movie ids referenced by either side of any conflict."""
    seen: set[str] = set()
    out: list[MovieId] = []
    for c in conflicts:
        for candidate_id, candidate_type in (
            (c.candidate_a_id, c.candidate_a_type),
            (c.candidate_b_id, c.candidate_b_type),
        ):
            if candidate_type is not MediaType.MOVIE or candidate_id in seen:
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
        resolved_at=conflict.resolved_at,
        resolution=None if conflict.resolution is None else conflict.resolution.value,
        winner_id=conflict.winner_id,
        resolution_source=(
            None if conflict.resolution_source is None else conflict.resolution_source.value
        ),
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
                files=[_build_file(f) for f in movie.files],
            )
    return ConflictCandidateSummary(
        media_id=media_id,
        media_type=media_type,
        title=None,
        year=None,
        files=[],
    )


def _build_file(file: MediaFile) -> ConflictCandidateFile:
    """Project a ``MediaFile`` variant into its display DTO."""
    return ConflictCandidateFile(
        file_path=file.file_path.value,
        resolution=file.resolution.value,
        file_size=file.file_size,
        video_codec=None if file.video_codec is None else file.video_codec.value,
        hdr_format=None if file.hdr_format is None else file.hdr_format.value,
        is_primary=file.is_primary,
    )


__all__ = ["ListConflictsUseCase"]
