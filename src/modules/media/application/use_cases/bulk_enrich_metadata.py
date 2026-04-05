"""Use case for bulk metadata enrichment of all media."""

from collections.abc import Awaitable, Callable

from src.modules.media.application.dtos.enrichment_dtos import (
    BulkEnrichInput,
    BulkEnrichOutput,
    EnrichMediaInput,
    EnrichMediaOutput,
)
from src.modules.media.application.use_cases.enrich_movie_metadata import (
    EnrichMovieMetadataUseCase,
)
from src.modules.media.application.use_cases.enrich_series_metadata import (
    EnrichSeriesMetadataUseCase,
)
from src.modules.media.domain.repositories import MovieRepository, SeriesRepository


class BulkEnrichMetadataUseCase:
    """Enrich all movies and series with external metadata.

    Iterates through all movies and series, enriching those that
    don't yet have metadata (or all if force=True).

    Args:
        enrich_movie: Use case for single movie enrichment.
        enrich_series: Use case for single series enrichment.
        movie_repository: Repository for listing movies.
        series_repository: Repository for listing series.
    """

    def __init__(
        self,
        enrich_movie: EnrichMovieMetadataUseCase,
        enrich_series: EnrichSeriesMetadataUseCase,
        movie_repository: MovieRepository,
        series_repository: SeriesRepository,
    ) -> None:
        self._enrich_movie = enrich_movie
        self._enrich_series = enrich_series
        self._movie_repository = movie_repository
        self._series_repository = series_repository

    async def execute(self, input_dto: BulkEnrichInput) -> BulkEnrichOutput:
        """Execute bulk metadata enrichment.

        Args:
            input_dto: Input with force flag.

        Returns:
            Summary of enrichment results.
        """
        errors: list[str] = []

        movies = await self._movie_repository.list_all()
        m_enriched, m_skipped = await self._enrich_all(
            items=[(str(m.id), m.title.value) for m in movies if m.id],
            enrich_fn=self._enrich_movie.execute,
            label="Movie",
            force=input_dto.force,
            errors=errors,
        )

        all_series = await self._series_repository.list_all()
        s_enriched, s_skipped = await self._enrich_all(
            items=[(str(s.id), s.title.value) for s in all_series if s.id],
            enrich_fn=self._enrich_series.execute,
            label="Series",
            force=input_dto.force,
            errors=errors,
        )

        return BulkEnrichOutput(
            movies_enriched=m_enriched,
            series_enriched=s_enriched,
            skipped=m_skipped + s_skipped,
            errors=errors,
        )

    @staticmethod
    async def _enrich_all(
        items: list[tuple[str, str]],
        enrich_fn: Callable[[EnrichMediaInput], Awaitable[EnrichMediaOutput]],
        label: str,
        *,
        force: bool,
        errors: list[str],
    ) -> tuple[int, int]:
        """Enrich a list of media items, collecting results and errors."""
        enriched = 0
        skipped = 0
        for media_id, title in items:
            try:
                result = await enrich_fn(EnrichMediaInput(media_id=media_id, force=force))
                if result.enriched:
                    enriched += 1
                elif result.error:
                    errors.append(f"{label} '{title}': {result.error}")
                else:
                    skipped += 1
            except Exception as e:
                errors.append(f"{label} '{title}': {e}")
        return enriched, skipped


__all__ = ["BulkEnrichMetadataUseCase"]
