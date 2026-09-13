"""ListMoviesUseCase - List movies in the library, paginated."""

from src.modules.media.application.dtos.movie_dtos import (
    ListMoviesInput,
    ListMoviesOutput,
    MovieSummaryOutput,
)
from src.modules.media.application.ports.profile_viewing_policy_port import (
    ProfileViewingPolicyPort,
)
from src.modules.media.application.unit_of_work import MediaUnitOfWorkFactory
from src.modules.media.application.use_cases._movie_summary_helpers import to_movie_summary
from src.modules.media.domain.entities import Movie
from src.shared_kernel.value_objects.profile_id import ProfileId


class ListMoviesUseCase:
    """List one page of movies using cursor-based pagination.

    Delegates the page query to ``MovieRepository.list_paginated`` and
    converts the resulting ``Movie`` entities into ``MovieSummaryOutput``
    DTOs. The cursor is passed through opaquely — the use case never
    decodes or encodes it, the repository owns that contract.

    Per ADR-010 and ADR-035, the page is restricted to what the caller's
    ``ViewingPolicy`` permits, resolved via ``ProfileViewingPolicyPort``. A
    deny-all profile short-circuits to an empty page without opening
    the UoW, which saves a round-trip.

    Example:
        >>> use_case = ListMoviesUseCase(uow_factory, profile_viewing_policy)
        >>> result = await use_case.execute(
        ...     ListMoviesInput(profile_id="prf_abc", limit=20)
        ... )
        >>> len(result.movies)
        20
        >>> result.has_more
        True
    """

    def __init__(
        self,
        uow_factory: MediaUnitOfWorkFactory,
        profile_viewing_policy: ProfileViewingPolicyPort,
    ) -> None:
        """Initialize the use case.

        Args:
            uow_factory: Factory that opens a fresh media Unit of Work.
            profile_viewing_policy: Port that resolves the caller's
                viewing policy.
        """
        self._uow_factory = uow_factory
        self._profile_viewing_policy = profile_viewing_policy

    async def execute(self, input_dto: ListMoviesInput) -> ListMoviesOutput:
        """Execute the use case.

        Args:
            input_dto: ``profile_id``, ``cursor`` (opaque), ``limit``,
                ``include_total``, and ``lang``.

        Returns:
            ``ListMoviesOutput`` with the page items, the next cursor,
            ``has_more``, and an optional ``total_count`` (only when
            ``include_total=True``).
        """
        policy = await self._profile_viewing_policy.find_for_profile(
            ProfileId(input_dto.profile_id)
        )
        if policy.denies_everything:
            return ListMoviesOutput(
                movies=[],
                next_cursor=None,
                has_more=False,
                total_count=0 if input_dto.include_total else None,
            )

        async with self._uow_factory() as uow:
            page = await uow.movies.list_paginated(
                cursor=input_dto.cursor,
                limit=input_dto.limit,
                include_total=input_dto.include_total,
                policy=policy,
                library_id=input_dto.library_id,
                has_tmdb_id=input_dto.has_tmdb_id,
                needs_enrichment_review=input_dto.needs_enrichment_review,
                q=input_dto.q,
            )

        return ListMoviesOutput(
            movies=[self._to_summary(movie, input_dto.lang) for movie in page.items],
            next_cursor=page.pagination.next_cursor,
            has_more=page.pagination.has_more,
            total_count=page.total_count,
        )

    @staticmethod
    def _to_summary(movie: Movie, lang: str = "en") -> MovieSummaryOutput:
        """Convert Movie entity to summary output."""
        return to_movie_summary(movie, lang)


__all__ = ["ListMoviesUseCase"]
