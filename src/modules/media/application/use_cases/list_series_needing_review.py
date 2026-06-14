"""Use case: list series the admin needs to relink manually."""

from src.modules.media.application.dtos.admin_relink_dtos import (
    ListSeriesNeedingReviewOutput,
    NeedsReviewSeriesOutput,
)
from src.modules.media.application.unit_of_work import MediaUnitOfWorkFactory
from src.modules.media.domain.entities import Series


class ListSeriesNeedingReviewUseCase:
    """Return series whose ``needs_enrichment_review`` flag is set.

    Backs the admin series "review queue" — small set in practice, so
    no pagination. Newest-flagged first comes from the repository's
    ``updated_at DESC`` order.

    The admin endpoint is global (no per-profile filter): the caller is
    already gated by ``current_admin_user``.

    Args:
        uow_factory: Factory that opens a fresh media Unit of Work.
    """

    def __init__(self, uow_factory: MediaUnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def execute(self) -> ListSeriesNeedingReviewOutput:
        """Return all series pending enrichment review."""
        async with self._uow_factory() as uow:
            series = await uow.series.find_needs_enrichment_review()
            return ListSeriesNeedingReviewOutput(
                series=[_to_output(s) for s in series],
            )


def _to_output(series: Series) -> NeedsReviewSeriesOutput:
    return NeedsReviewSeriesOutput(
        id=str(series.id),
        title=series.title.value,
        year=series.start_year.value,
        tmdb_id=series.tmdb_id.value if series.tmdb_id else None,
    )


__all__ = ["ListSeriesNeedingReviewUseCase"]
