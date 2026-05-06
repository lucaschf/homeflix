"""GetRelatedSeriesUseCase — TMDB recommendations filtered by library."""

from dataclasses import dataclass

from src.modules.media.application.dtos.series_dtos import SeriesSummaryOutput
from src.modules.media.application.ports import MetadataProvider
from src.modules.media.application.ports.profile_library_access_port import (
    ProfileLibraryAccessPort,
)
from src.modules.media.application.unit_of_work import MediaUnitOfWorkFactory
from src.modules.media.application.use_cases._series_summary_helpers import to_series_summary
from src.modules.media.domain.value_objects import SeriesId


@dataclass(frozen=True)
class GetRelatedSeriesInput:
    """Input for ``GetRelatedSeriesUseCase``.

    Attributes:
        profile_id: Caller's prefixed profile id. The use case
            consults ``ProfileLibraryAccessPort`` and restricts both
            the source lookup and the related-series intersection to
            libraries the profile may see; a deny-all profile yields
            an empty list without opening a UoW.
        series_id: External id of the series to look up recommendations for.
        lang: Language for localized fields on the response.
        limit: Maximum number of related series to return.
    """

    profile_id: str
    series_id: str
    lang: str = "en"
    limit: int = 12


class GetRelatedSeriesUseCase:
    """Return series in the library that TMDB recommends for the input.

    Pulls TMDB's recommendation list for the input series (falling back
    to TMDB's "similar" endpoint when recommendations is empty), then
    intersects with the local catalog by ``tmdb_id``. The TMDB ordering
    (by relevance) is preserved on the way out.

    The feature is best-effort polish: any failure (series not found,
    series not enriched with TMDB id, provider unavailable, no overlap
    with local catalog) yields an empty list rather than raising — the
    UI simply doesn't render the carousel.

    Example:
        >>> use_case = GetRelatedSeriesUseCase(uow_factory, tmdb_client)
        >>> result = await use_case.execute(GetRelatedSeriesInput("ser_abc"))
        >>> [s.title for s in result]
        ['Breaking Bad', 'Better Call Saul', ...]
    """

    def __init__(
        self,
        uow_factory: MediaUnitOfWorkFactory,
        metadata_provider: MetadataProvider,
        profile_library_access: ProfileLibraryAccessPort,
    ) -> None:
        self._uow_factory = uow_factory
        self._metadata = metadata_provider
        self._profile_library_access = profile_library_access

    async def execute(self, input_dto: GetRelatedSeriesInput) -> list[SeriesSummaryOutput]:
        """Run the lookup.

        A deny-all profile yields an empty list without opening a UoW.
        When the source series itself is outside the caller's ACL the
        method also returns an empty list — best-effort polish, no
        404 raised here.
        """
        allowed = await self._profile_library_access.find_for_profile(input_dto.profile_id)
        if not allowed:
            return []

        async with self._uow_factory() as uow:
            source = await uow.series.find_by_id(
                SeriesId(input_dto.series_id), allowed_library_ids=allowed
            )
            if source is None or source.tmdb_id is None:
                return []

            tmdb_ids = await self._metadata.get_series_recommendations(source.tmdb_id.value)
            if not tmdb_ids:
                return []

            # Trim before hitting the DB so a TMDB result of 50 doesn't
            # cost us 50 rows when the carousel only shows ``limit``.
            # Slight over-fetch (2x) so a few catalog gaps don't leave
            # the carousel sparse.
            candidate_ids = tmdb_ids[: input_dto.limit * 2]
            local = await uow.series.find_by_tmdb_ids(candidate_ids, allowed_library_ids=allowed)

        # Preserve TMDB's relevance ordering by iterating the request
        # list rather than the dict's insertion order.
        ordered: list[SeriesSummaryOutput] = []
        for tid in candidate_ids:
            series = local.get(tid)
            if series is None:
                continue
            ordered.append(to_series_summary(series, input_dto.lang))
            if len(ordered) >= input_dto.limit:
                break
        return ordered


__all__ = ["GetRelatedSeriesInput", "GetRelatedSeriesUseCase"]
