"""ListSeriesUseCase - List series in the library, paginated."""

from src.modules.media.application.dtos.series_dtos import (
    ListSeriesInput,
    ListSeriesOutput,
)
from src.modules.media.application.ports.profile_viewing_policy_port import (
    ProfileViewingPolicyPort,
)
from src.modules.media.application.unit_of_work import MediaUnitOfWorkFactory
from src.modules.media.application.use_cases._series_summary_helpers import to_series_summary
from src.shared_kernel.value_objects.profile_id import ProfileId


class ListSeriesUseCase:
    """List one page of series using cursor-based pagination.

    Delegates the page query to ``SeriesRepository.list_paginated`` and
    converts the resulting ``Series`` entities into
    ``SeriesSummaryOutput`` DTOs. The cursor is passed through
    opaquely.

    Per ADR-010 and ADR-035, the page is restricted to what the caller's
    ``ViewingPolicy`` permits, resolved via ``ProfileViewingPolicyPort``. A
    deny-all profile short-circuits to an empty page without opening
    the UoW.

    Example:
        >>> use_case = ListSeriesUseCase(uow_factory, profile_viewing_policy)
        >>> result = await use_case.execute(ListSeriesInput(profile_id="prf_abc"))
        >>> len(result.series)
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

    async def execute(self, input_dto: ListSeriesInput) -> ListSeriesOutput:
        """Execute the use case.

        Args:
            input_dto: ``profile_id``, ``cursor`` (opaque), ``limit``,
                ``include_total``, and ``lang``.

        Returns:
            ``ListSeriesOutput`` with the page items, the next cursor,
            ``has_more``, and an optional ``total_count`` (only when
            ``include_total=True``).
        """
        policy = await self._profile_viewing_policy.find_for_profile(
            ProfileId(input_dto.profile_id)
        )
        if policy.denies_everything:
            return ListSeriesOutput(
                series=[],
                next_cursor=None,
                has_more=False,
                total_count=0 if input_dto.include_total else None,
            )

        async with self._uow_factory() as uow:
            page = await uow.series.list_paginated(
                cursor=input_dto.cursor,
                limit=input_dto.limit,
                include_total=input_dto.include_total,
                policy=policy,
                library_id=input_dto.library_id,
                has_tmdb_id=input_dto.has_tmdb_id,
                q=input_dto.q,
            )

        return ListSeriesOutput(
            series=[to_series_summary(s, input_dto.lang) for s in page.items],
            next_cursor=page.pagination.next_cursor,
            has_more=page.pagination.has_more,
            total_count=page.total_count,
        )


__all__ = ["ListSeriesUseCase"]
