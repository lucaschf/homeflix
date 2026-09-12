"""ListRecentlyAddedMoviesUseCase - Top N most recently added movies."""

from src.modules.media.application.dtos.movie_dtos import (
    ListRecentlyAddedMoviesInput,
    ListRecentlyAddedMoviesOutput,
)
from src.modules.media.application.ports.profile_viewing_policy_port import (
    ProfileViewingPolicyPort,
)
from src.modules.media.application.unit_of_work import MediaUnitOfWorkFactory
from src.modules.media.application.use_cases._movie_summary_helpers import to_movie_summary
from src.shared_kernel.value_objects.profile_id import ProfileId


class ListRecentlyAddedMoviesUseCase:
    """Return the most recently added movies for the home-page carousel.

    Bounded "top N" projection — no cursor, no pagination metadata.
    The home-page carousel renders the full slice and the user goes
    to the catalog page if they want to keep browsing.

    Per ADR-010 and ADR-035, results are restricted to what the caller's
    ``ViewingPolicy`` permits, resolved via ``ProfileViewingPolicyPort``. A
    deny-all profile short-circuits to an empty list without opening
    the UoW.

    Example:
        >>> use_case = ListRecentlyAddedMoviesUseCase(
        ...     uow_factory, profile_viewing_policy
        ... )
        >>> result = await use_case.execute(
        ...     ListRecentlyAddedMoviesInput(profile_id="prf_abc", limit=20)
        ... )
        >>> len(result.movies)
        20
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

    async def execute(
        self, input_dto: ListRecentlyAddedMoviesInput
    ) -> ListRecentlyAddedMoviesOutput:
        """Execute the use case.

        Args:
            input_dto: ``profile_id``, ``limit`` (max items) and ``lang``.

        Returns:
            ``ListRecentlyAddedMoviesOutput`` with newest-first
            movie summaries.
        """
        policy = await self._profile_viewing_policy.find_for_profile(
            ProfileId(input_dto.profile_id)
        )
        if policy.denies_everything:
            return ListRecentlyAddedMoviesOutput(movies=[])

        async with self._uow_factory() as uow:
            movies = await uow.movies.list_recently_added(
                input_dto.limit,
                policy=policy,
            )

        return ListRecentlyAddedMoviesOutput(
            movies=[to_movie_summary(movie, input_dto.lang) for movie in movies],
        )


__all__ = ["ListRecentlyAddedMoviesUseCase"]
