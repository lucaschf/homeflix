"""ListMoviesUseCase - List movies in the library, paginated."""

from src.modules.media.application.dtos.movie_dtos import (
    ListMoviesInput,
    ListMoviesOutput,
    MovieSummaryOutput,
)
from src.modules.media.application.ports.profile_library_access_port import (
    ProfileLibraryAccessPort,
)
from src.modules.media.application.unit_of_work import MediaUnitOfWorkFactory
from src.modules.media.application.use_cases._movie_summary_helpers import to_movie_summary
from src.modules.media.domain.entities import Movie


class ListMoviesUseCase:
    """List one page of movies using cursor-based pagination.

    Delegates the page query to ``MovieRepository.list_paginated`` and
    converts the resulting ``Movie`` entities into ``MovieSummaryOutput``
    DTOs. The cursor is passed through opaquely — the use case never
    decodes or encodes it, the repository owns that contract.

    Per ADR-010, the page is restricted to the caller's
    ``Profile.allowed_library_ids`` via ``ProfileLibraryAccessPort``. A
    deny-all profile short-circuits to an empty page without opening
    the UoW — that avoids dialect-specific ``WHERE library_id IN ()``
    issues and saves a round-trip.

    Example:
        >>> use_case = ListMoviesUseCase(uow_factory, profile_library_access)
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
        allowed = await self._profile_library_access.find_for_profile(input_dto.profile_id)
        if not allowed:
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
                allowed_library_ids=allowed,
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
