"""ListCreditsStatusUseCase — admin observability of credits detection."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.modules.media.application.dtos.credits_dtos import (
    CreditsStatusItem,
    CreditsStatusOutput,
    ListCreditsStatusInput,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from src.modules.media.application.unit_of_work import MediaUnitOfWorkFactory
    from src.modules.media.domain.repositories.movie_repository import CreditsStatusRow

_MOVIE = "movie"


class ListCreditsStatusUseCase:
    """List titles by credits-detection state, with per-state counts.

    Read-only admin observability so an operator can see which movies /
    episodes have been processed (``COMPLETED`` / ``NO_CREDITS_FOUND`` /
    ``FAILED`` / ``NOT_STARTED``) and jump to the manual editor for the
    misses. Movies and episodes are queried separately (one media type
    per call) since they live in different aggregates.

    Example:
        >>> use_case = ListCreditsStatusUseCase(uow_factory)
        >>> page = await use_case.execute(
        ...     ListCreditsStatusInput(media_type="movie", state="NO_CREDITS_FOUND"),
        ... )
    """

    def __init__(self, uow_factory: MediaUnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def execute(self, input_dto: ListCreditsStatusInput) -> CreditsStatusOutput:
        """Return a page of status rows + the unfiltered per-state counts."""
        is_movie = input_dto.media_type == _MOVIE
        async with self._uow_factory() as uow:
            if is_movie:
                counts = await uow.movies.count_credits_states()
                rows, total = await uow.movies.list_credits_status(
                    input_dto.state, input_dto.limit, input_dto.offset
                )
            else:
                counts = await uow.series.count_episode_credits_states()
                rows, total = await uow.series.list_episode_credits_status(
                    input_dto.state, input_dto.limit, input_dto.offset
                )

        items = _to_items(rows, input_dto.media_type)
        return CreditsStatusOutput(items=items, total=total, counts=dict(counts))


def _to_items(rows: Sequence[CreditsStatusRow], media_type: str) -> list[CreditsStatusItem]:
    return [
        CreditsStatusItem(
            media_id=row.media_id,
            media_type=media_type,
            title=row.title,
            state=row.state,
            start_seconds=row.start_seconds,
            source=row.source,
            confidence=row.confidence,
            series_id=row.series_id,
            season_number=row.season_number,
            episode_number=row.episode_number,
        )
        for row in rows
    ]


__all__ = ["ListCreditsStatusUseCase"]
