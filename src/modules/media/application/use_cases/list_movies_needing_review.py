"""Use case: list movies the admin needs to relink manually."""

from src.modules.media.application.dtos.admin_relink_dtos import (
    ListMoviesNeedingReviewOutput,
    NeedsReviewMovieOutput,
)
from src.modules.media.application.unit_of_work import MediaUnitOfWorkFactory
from src.modules.media.domain.entities import Movie


class ListMoviesNeedingReviewUseCase:
    """Return movies whose ``needs_enrichment_review`` flag is set.

    Backs the admin "review queue" — small set in practice (a few
    rows per few hundred movies), so no pagination. Newest-flagged
    first comes from the repository's ``updated_at DESC`` order.

    The admin endpoint is global (no per-profile filter): the user
    triggering it is already gated by ``current_admin_user``.

    Args:
        uow_factory: Factory that opens a fresh media Unit of Work.
    """

    def __init__(self, uow_factory: MediaUnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def execute(self) -> ListMoviesNeedingReviewOutput:
        """Return all movies pending enrichment review."""
        async with self._uow_factory() as uow:
            movies = await uow.movies.find_needs_enrichment_review()
            return ListMoviesNeedingReviewOutput(
                movies=[_to_output(m) for m in movies],
            )


def _to_output(movie: Movie) -> NeedsReviewMovieOutput:
    primary = movie.primary_file
    return NeedsReviewMovieOutput(
        id=str(movie.id),
        title=movie.title.value,
        year=movie.year.value,
        file_path=primary.file_path.value if primary else None,
    )


__all__ = ["ListMoviesNeedingReviewUseCase"]
