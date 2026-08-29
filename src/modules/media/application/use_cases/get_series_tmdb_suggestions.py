"""Use case: live TMDB picker payload for the series relink flow."""

from src.building_blocks.application.errors import ResourceNotFoundException
from src.modules.media.application.dtos.admin_relink_dtos import (
    GetSeriesTmdbSuggestionsInput,
    GetSeriesTmdbSuggestionsOutput,
    TmdbSuggestionOutput,
)
from src.modules.media.application.unit_of_work import MediaUnitOfWorkFactory
from src.modules.media.domain.value_objects import SeriesId
from src.modules.metadata.application.ports.metadata_provider_port import (
    MetadataProvider,
    SearchCandidate,
)


class GetSeriesTmdbSuggestionsUseCase:
    """Return TMDB TV candidates for a series needing review.

    Loads the series to seed the search with its stored title and
    start year, then issues ``/search/tv``. When the year-hinted query
    returns nothing, retries without the year so the picker still shows
    something for the operator to pick visually.

    Only TV candidates are returned — re-pointing a series at a movie
    would be the inverse promotion, which isn't supported.

    Args:
        uow_factory: Factory that opens a fresh media Unit of Work.
        metadata_provider: TMDB-side metadata port.
        candidates_limit: Maximum number of suggestions to return.
    """

    def __init__(
        self,
        uow_factory: MediaUnitOfWorkFactory,
        metadata_provider: MetadataProvider,
        candidates_limit: int = 5,
    ) -> None:
        self._uow_factory = uow_factory
        self._provider = metadata_provider
        self._limit = candidates_limit

    async def execute(
        self,
        input_dto: GetSeriesTmdbSuggestionsInput,
    ) -> GetSeriesTmdbSuggestionsOutput:
        """Return TMDB TV candidates for the picker UI."""
        async with self._uow_factory() as uow:
            series = await uow.series.find_by_id(SeriesId(input_dto.series_id))
            if not series:
                raise ResourceNotFoundException.for_resource("Series", input_dto.series_id)
            title = series.title.value
            year = series.start_year.value

        candidates = await self._candidates_with_fallback(title, year)

        return GetSeriesTmdbSuggestionsOutput(
            series_id=input_dto.series_id,
            series=[_to_output(c) for c in candidates],
        )

    async def _candidates_with_fallback(
        self,
        title: str,
        year: int | None,
    ) -> list[SearchCandidate]:
        """Search with year first; if empty, drop the year hint."""
        candidates = await self._provider.find_series_candidates(title, year, self._limit)
        if not candidates and year is not None:
            candidates = await self._provider.find_series_candidates(title, None, self._limit)
        return candidates


def _to_output(candidate: SearchCandidate) -> TmdbSuggestionOutput:
    return TmdbSuggestionOutput(
        tmdb_id=candidate.tmdb_id,
        media_type=candidate.media_type,
        title=candidate.title,
        year=candidate.year,
        overview=candidate.overview,
        poster_url=candidate.poster_url,
    )


__all__ = ["GetSeriesTmdbSuggestionsUseCase"]
