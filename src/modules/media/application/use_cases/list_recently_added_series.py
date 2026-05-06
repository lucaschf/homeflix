"""ListRecentlyAddedSeriesUseCase - Top N most recently added series."""

from src.modules.media.application.dtos.series_dtos import (
    ListRecentlyAddedSeriesInput,
    ListRecentlyAddedSeriesOutput,
)
from src.modules.media.application.ports.profile_library_access_port import (
    ProfileLibraryAccessPort,
)
from src.modules.media.application.unit_of_work import MediaUnitOfWorkFactory
from src.modules.media.application.use_cases._series_summary_helpers import to_series_summary


class ListRecentlyAddedSeriesUseCase:
    """Return the most recently added series for the home-page carousel.

    Bounded "top N" projection — mirror of
    ``ListRecentlyAddedMoviesUseCase`` for the series side.

    Per ADR-010, results are restricted to the caller's
    ``Profile.allowed_library_ids`` via ``ProfileLibraryAccessPort``. A
    deny-all profile short-circuits to an empty list without opening
    the UoW.

    Example:
        >>> use_case = ListRecentlyAddedSeriesUseCase(
        ...     uow_factory, profile_library_access
        ... )
        >>> result = await use_case.execute(
        ...     ListRecentlyAddedSeriesInput(profile_id="prf_abc", limit=20)
        ... )
        >>> len(result.series)
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
        self, input_dto: ListRecentlyAddedSeriesInput
    ) -> ListRecentlyAddedSeriesOutput:
        """Execute the use case.

        Args:
            input_dto: ``profile_id``, ``limit`` (max items) and ``lang``.

        Returns:
            ``ListRecentlyAddedSeriesOutput`` with newest-first
            series summaries.
        """
        allowed = await self._profile_library_access.find_for_profile(input_dto.profile_id)
        if not allowed:
            return ListRecentlyAddedSeriesOutput(series=[])

        async with self._uow_factory() as uow:
            series_list = await uow.series.list_recently_added(
                input_dto.limit,
                allowed_library_ids=allowed,
            )

        return ListRecentlyAddedSeriesOutput(
            series=[to_series_summary(s, input_dto.lang) for s in series_list],
        )


__all__ = ["ListRecentlyAddedSeriesUseCase"]
