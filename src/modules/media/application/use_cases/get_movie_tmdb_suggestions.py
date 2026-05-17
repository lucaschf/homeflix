"""Use case: live TMDB picker payload for the admin relink flow."""

import asyncio

from src.building_blocks.application.errors import ResourceNotFoundException
from src.modules.media.application.dtos.admin_relink_dtos import (
    GetMovieTmdbSuggestionsInput,
    GetMovieTmdbSuggestionsOutput,
    TmdbSuggestionOutput,
)
from src.modules.media.application.ports import MetadataProvider, SearchCandidate
from src.modules.media.application.unit_of_work import MediaUnitOfWorkFactory
from src.modules.media.domain.value_objects import MovieId


class GetMovieTmdbSuggestionsUseCase:
    """Return TMDB movie + TV candidates for an unenriched movie.

    Loads the movie to seed the search with its scanner-extracted
    title and year, then issues both ``/search/movie`` and
    ``/search/tv`` in parallel. When the year-hinted query returns
    nothing, retries without the year — the admin picker is meant
    to show *something* so the operator can pick visually.

    Args:
        uow_factory: Factory that opens a fresh media Unit of Work.
        metadata_provider: TMDB-side metadata port. The admin
            endpoint registers the primary provider (TMDB).
        candidates_limit: Maximum number of suggestions per type.
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
        input_dto: GetMovieTmdbSuggestionsInput,
    ) -> GetMovieTmdbSuggestionsOutput:
        """Return TMDB movie + TV candidates for the picker UI."""
        async with self._uow_factory() as uow:
            movie = await uow.movies.find_by_id(MovieId(input_dto.movie_id))
            if not movie:
                raise ResourceNotFoundException.for_resource("Movie", input_dto.movie_id)
            title = movie.title.value
            year = movie.year.value

        movie_candidates, series_candidates = await asyncio.gather(
            self._candidates_with_fallback(title, year, kind="movie"),
            self._candidates_with_fallback(title, year, kind="series"),
        )

        return GetMovieTmdbSuggestionsOutput(
            movie_id=input_dto.movie_id,
            movies=[_to_output(c) for c in movie_candidates],
            series=[_to_output(c) for c in series_candidates],
        )

    async def _candidates_with_fallback(
        self,
        title: str,
        year: int | None,
        *,
        kind: str,
    ) -> list[SearchCandidate]:
        """Search with year first; if empty, drop the year hint.

        TMDB's ``year`` / ``first_air_date_year`` is a soft ranking
        signal — when it produces no hits, falling back to the
        unfiltered query usually surfaces the title elsewhere on the
        timeline (e.g. a remake series for a folder marked with the
        original-film year).
        """
        fetch = (
            self._provider.find_movie_candidates
            if kind == "movie"
            else self._provider.find_series_candidates
        )
        candidates = await fetch(title, year, self._limit)
        if not candidates and year is not None:
            candidates = await fetch(title, None, self._limit)
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


__all__ = ["GetMovieTmdbSuggestionsUseCase"]
