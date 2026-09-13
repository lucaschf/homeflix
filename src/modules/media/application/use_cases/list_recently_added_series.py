"""ListRecentlyAddedSeriesUseCase - Top N most recently added series."""

from src.modules.media.application.dtos.series_dtos import (
    ListRecentlyAddedSeriesInput,
    ListRecentlyAddedSeriesOutput,
)
from src.modules.media.application.ports.profile_viewing_policy_port import (
    ProfileViewingPolicyPort,
)
from src.modules.media.application.unit_of_work import MediaUnitOfWorkFactory
from src.modules.media.application.use_cases._series_summary_helpers import to_series_summary
from src.shared_kernel.value_objects.profile_id import ProfileId


class ListRecentlyAddedSeriesUseCase:
    """Return the most recently added series for the home-page carousel.

    Bounded "top N" projection — mirror of
    ``ListRecentlyAddedMoviesUseCase`` for the series side.

    Per ADR-010 and ADR-035, results are restricted to what the caller's
    ``ViewingPolicy`` permits, resolved via ``ProfileViewingPolicyPort``. A
    deny-all profile short-circuits to an empty list without opening
    the UoW.

    Example:
        >>> use_case = ListRecentlyAddedSeriesUseCase(
        ...     uow_factory, profile_viewing_policy
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
        self, input_dto: ListRecentlyAddedSeriesInput
    ) -> ListRecentlyAddedSeriesOutput:
        """Execute the use case.

        Args:
            input_dto: ``profile_id``, ``limit`` (max items) and ``lang``.

        Returns:
            ``ListRecentlyAddedSeriesOutput`` with newest-first
            series summaries.
        """
        policy = await self._profile_viewing_policy.find_for_profile(
            ProfileId(input_dto.profile_id)
        )
        if policy.denies_everything:
            return ListRecentlyAddedSeriesOutput(series=[])

        async with self._uow_factory() as uow:
            series_list = await uow.series.list_recently_added(
                input_dto.limit,
                policy=policy,
            )

        return ListRecentlyAddedSeriesOutput(
            series=[to_series_summary(s, input_dto.lang) for s in series_list],
        )


__all__ = ["ListRecentlyAddedSeriesUseCase"]
