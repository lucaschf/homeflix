"""ListSeriesUseCase - List series in the library, paginated."""

from src.modules.media.application.dtos.series_dtos import (
    ListSeriesInput,
    ListSeriesOutput,
)
from src.modules.media.application.ports.profile_library_access_port import (
    ProfileLibraryAccessPort,
)
from src.modules.media.application.unit_of_work import MediaUnitOfWorkFactory
from src.modules.media.application.use_cases._series_summary_helpers import to_series_summary


class ListSeriesUseCase:
    """List one page of series using cursor-based pagination.

    Delegates the page query to ``SeriesRepository.list_paginated`` and
    converts the resulting ``Series`` entities into
    ``SeriesSummaryOutput`` DTOs. The cursor is passed through
    opaquely.

    Per ADR-010, the page is restricted to the caller's
    ``Profile.allowed_library_ids`` via ``ProfileLibraryAccessPort``. A
    deny-all profile short-circuits to an empty page without opening
    the UoW.

    Example:
        >>> use_case = ListSeriesUseCase(uow_factory, profile_library_access)
        >>> result = await use_case.execute(ListSeriesInput(profile_id="prf_abc"))
        >>> len(result.series)
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
        allowed = await self._profile_library_access.find_for_profile(input_dto.profile_id)
        if not allowed:
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
                allowed_library_ids=allowed,
            )

        return ListSeriesOutput(
            series=[to_series_summary(s, input_dto.lang) for s in page.items],
            next_cursor=page.pagination.next_cursor,
            has_more=page.pagination.has_more,
            total_count=page.total_count,
        )


__all__ = ["ListSeriesUseCase"]
