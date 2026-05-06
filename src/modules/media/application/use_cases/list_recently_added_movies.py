"""ListRecentlyAddedMoviesUseCase - Top N most recently added movies."""

from src.modules.media.application.dtos.movie_dtos import (
    ListRecentlyAddedMoviesInput,
    ListRecentlyAddedMoviesOutput,
)
from src.modules.media.application.ports.profile_library_access_port import (
    ProfileLibraryAccessPort,
)
from src.modules.media.application.unit_of_work import MediaUnitOfWorkFactory
from src.modules.media.application.use_cases._movie_summary_helpers import to_movie_summary


class ListRecentlyAddedMoviesUseCase:
    """Return the most recently added movies for the home-page carousel.

    Bounded "top N" projection — no cursor, no pagination metadata.
    The home-page carousel renders the full slice and the user goes
    to the catalog page if they want to keep browsing.

    Per ADR-010, results are restricted to the caller's
    ``Profile.allowed_library_ids`` via ``ProfileLibraryAccessPort``. A
    deny-all profile short-circuits to an empty list without opening
    the UoW.

    Example:
        >>> use_case = ListRecentlyAddedMoviesUseCase(
        ...     uow_factory, profile_library_access
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
        profile_library_access: ProfileLibraryAccessPort,
    ) -> None:
        """Initialize the use case.

        Args:
            uow_factory: Factory that opens a fresh media Unit of Work.
            profile_library_access: Port that resolves the caller's
                allowed library_ids.
        """
        self._uow_factory = uow_factory
        self._profile_library_access = profile_library_access

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
        allowed = await self._profile_library_access.find_for_profile(input_dto.profile_id)
        if not allowed:
            return ListRecentlyAddedMoviesOutput(movies=[])

        async with self._uow_factory() as uow:
            movies = await uow.movies.list_recently_added(
                input_dto.limit,
                allowed_library_ids=allowed,
            )

        return ListRecentlyAddedMoviesOutput(
            movies=[to_movie_summary(movie, input_dto.lang) for movie in movies],
        )


__all__ = ["ListRecentlyAddedMoviesUseCase"]
