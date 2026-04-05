"""Use case for enriching a movie with external metadata."""

from src.building_blocks.application.errors import ResourceNotFoundException
from src.modules.media.application.dtos.enrichment_dtos import (
    EnrichMediaInput,
    EnrichMediaOutput,
)
from src.modules.media.application.ports import MediaMetadata, MetadataProvider
from src.modules.media.domain.entities import Movie
from src.modules.media.domain.repositories import MovieRepository
from src.modules.media.domain.value_objects import Duration, Genre, MovieId, Title, Year


class EnrichMovieMetadataUseCase:
    """Enrich a movie entity with metadata from external providers.

    Searches the primary provider first, falls back to the secondary
    if the primary returns no results.

    Args:
        movie_repository: Repository for movie persistence.
        primary_provider: Primary metadata provider (e.g., TMDB).
        fallback_provider: Optional fallback provider (e.g., OMDb).
    """

    def __init__(
        self,
        movie_repository: MovieRepository,
        primary_provider: MetadataProvider,
        fallback_provider: MetadataProvider | None = None,
    ) -> None:
        self._movie_repository = movie_repository
        self._primary = primary_provider
        self._fallback = fallback_provider

    async def execute(self, input_dto: EnrichMediaInput) -> EnrichMediaOutput:
        """Execute movie metadata enrichment.

        Args:
            input_dto: Input with movie ID and force flag.

        Returns:
            Enrichment result with success/failure status.
        """
        movie = await self._movie_repository.find_by_id(MovieId(input_dto.media_id))
        if not movie:
            raise ResourceNotFoundException.for_resource("Movie", input_dto.media_id)

        if movie.tmdb_id and not input_dto.force:
            return EnrichMediaOutput(media_id=input_dto.media_id, enriched=False, provider=None)

        metadata, provider_name = await self._fetch_metadata(movie)
        if not metadata:
            return EnrichMediaOutput(
                media_id=input_dto.media_id,
                enriched=False,
                error="No metadata found from any provider",
            )

        movie = _apply_movie_metadata(movie, metadata)
        await self._movie_repository.save(movie)

        return EnrichMediaOutput(media_id=input_dto.media_id, enriched=True, provider=provider_name)

    async def _fetch_metadata(self, movie: Movie) -> tuple[MediaMetadata | None, str | None]:
        """Try primary provider, then fallback."""
        if movie.tmdb_id:
            metadata = await self._primary.get_movie_by_id(movie.tmdb_id)
            if metadata:
                return metadata, "tmdb"

        metadata = await self._primary.search_movie(movie.title.value, movie.year.value)
        if metadata:
            return metadata, "tmdb"

        if self._fallback:
            metadata = await self._fallback.search_movie(movie.title.value, movie.year.value)
            if metadata:
                return metadata, "omdb"

        return None, None


def _apply_movie_metadata(movie: Movie, metadata: MediaMetadata) -> Movie:
    """Apply metadata fields to a movie entity."""
    updates: dict[str, object] = {}

    if metadata.synopsis and not movie.synopsis:
        updates["synopsis"] = metadata.synopsis
    if metadata.tmdb_id:
        updates["tmdb_id"] = metadata.tmdb_id
    if metadata.imdb_id:
        updates["imdb_id"] = metadata.imdb_id
    if metadata.original_title:
        updates["original_title"] = Title(metadata.original_title)
    if metadata.duration_seconds and movie.duration.value == 0:
        updates["duration"] = Duration(metadata.duration_seconds)
    if metadata.year:
        updates["year"] = Year(metadata.year)
    if metadata.genres and not movie.genres:
        updates["genres"] = [Genre(g) for g in metadata.genres]

    if updates:
        movie = movie.with_updates(**updates)

    return movie


__all__ = ["EnrichMovieMetadataUseCase"]
