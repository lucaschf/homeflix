"""Use case for enriching a movie with external metadata."""

import logging

from src.building_blocks.application.errors import ResourceNotFoundException
from src.modules.media.application.dtos.enrichment_dtos import (
    EnrichMediaInput,
    EnrichMediaOutput,
)
from src.modules.media.application.ports import MediaMetadata, MetadataProvider
from src.modules.media.domain.entities import Movie
from src.modules.media.domain.repositories import MovieRepository
from src.modules.media.domain.value_objects import (
    Duration,
    Genre,
    ImageUrl,
    ImdbId,
    MovieId,
    Title,
    TmdbId,
    Year,
)

_logger = logging.getLogger(__name__)


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

        # Re-fetch with localization if TMDB provider supports it
        if metadata.tmdb_id and hasattr(self._primary, "get_movie_localized"):
            get_localized = self._primary.get_movie_localized
            localized_meta: MediaMetadata | None = await get_localized(metadata.tmdb_id)
            if localized_meta is not None:
                metadata = localized_meta

        movie = _apply_movie_metadata(movie, metadata)
        await self._movie_repository.save(movie)

        return EnrichMediaOutput(media_id=input_dto.media_id, enriched=True, provider=provider_name)

    async def _fetch_metadata(self, movie: Movie) -> tuple[MediaMetadata | None, str | None]:
        """Try primary provider, then fallback.

        Searches with original title first, then retries with a
        cleaned title (quality tags removed) and without year.
        """
        if movie.tmdb_id:
            metadata = await self._primary.get_movie_by_id(movie.tmdb_id.value)
            if metadata:
                return metadata, "tmdb"

        title = movie.title.value
        year = movie.year.value

        # Try with original title + year
        metadata = await self._primary.search_movie(title, year)
        if metadata:
            return metadata, "tmdb"

        # Retry with cleaned title (remove quality tags) and no year
        clean = _clean_title(title)
        if clean != title:
            metadata = await self._primary.search_movie(clean)
            if metadata:
                return metadata, "tmdb"

        # Retry with just the title, no year
        metadata = await self._primary.search_movie(title)
        if metadata:
            return metadata, "tmdb"

        if self._fallback:
            metadata = await self._fallback.search_movie(clean or title)
            if metadata:
                return metadata, "omdb"

        _logger.warning("No metadata found for movie %r", title)
        return None, None


def _clean_title(title: str) -> str:
    """Remove common quality tags and noise from a title for better search."""
    import re

    # Remove words containing resolution (e.g. "TetraBD720p", "1080p", "FHD")
    result = re.sub(r"\S*\d{3,4}p\S*", "", title, flags=re.IGNORECASE)

    # Remove known tags
    patterns = [
        r"\b(?:4K|UHD|FHD|HD|SD)\b",
        r"\b(?:BluRay|BDRip|BRRip|WEB-?DL|WEB-?Rip|HDTV|DVDRip|REMUX)\b",
        r"\b(?:HEVC|H\.?265|H\.?264|x264|x265|AV1|VP9|MPEG4)\b",
        r"\b(?:HDR10\+?|HDR|DolbyVision|DV|HLG)\b",
        r"\b(?:DTS(?:-HD)?(?:\.?MA)?|TrueHD|Atmos|AAC|AC3|FLAC|EAC3)\b",
        r"\b(?:PROPER|REPACK|EXTENDED|UNRATED|IMAX|DC)\b",
        r"\b(?:TetraBD|MemoriadaTV|YIFY|RARBG|NTb|FGT|EVO|SPARKS)\b",
        r"\b\d{1,2}\.\d\b",  # audio channels like 5.1
        r"\[.*?\]",
        r"\(.*?\)",
    ]
    for pattern in patterns:
        result = re.sub(pattern, "", result, flags=re.IGNORECASE)

    # Remove standalone 2-digit numbers (e.g. "86" from year in filename)
    result = re.sub(r"\b\d{2}\b", "", result)

    # Clean up whitespace and trailing punctuation
    result = re.sub(r"\s+", " ", result).strip().strip("-._")
    return result


def _apply_movie_metadata(movie: Movie, metadata: MediaMetadata) -> Movie:
    """Apply metadata fields to a movie entity."""
    updates: dict[str, object] = {}

    if metadata.title:
        updates["title"] = Title(metadata.title)
    if metadata.synopsis and not movie.synopsis:
        updates["synopsis"] = metadata.synopsis
    if metadata.tmdb_id:
        updates["tmdb_id"] = TmdbId(metadata.tmdb_id)
    if metadata.imdb_id:
        updates["imdb_id"] = ImdbId(metadata.imdb_id)
    if metadata.original_title:
        updates["original_title"] = Title(metadata.original_title)
    if metadata.duration_seconds and movie.duration.value == 0:
        updates["duration"] = Duration(metadata.duration_seconds)
    if metadata.year:
        updates["year"] = Year(metadata.year)
    if metadata.genres and not movie.genres:
        updates["genres"] = [Genre(g) for g in metadata.genres]
    if metadata.poster_url and not movie.poster_path:
        updates["poster_path"] = ImageUrl(metadata.poster_url)
    if metadata.backdrop_url and not movie.backdrop_path:
        updates["backdrop_path"] = ImageUrl(metadata.backdrop_url)

    _apply_credits(updates, movie, metadata)

    if updates:
        movie = movie.with_updates(**updates)

    return movie


def _apply_credits(
    updates: dict[str, object],
    movie: Movie,
    metadata: MediaMetadata,
) -> None:
    """Apply cast/director/writer credits from metadata if not already present."""
    if metadata.cast and not movie.cast:
        updates["cast"] = [p.name for p in metadata.cast]
    if metadata.directors and not movie.directors:
        updates["directors"] = [p.name for p in metadata.directors]
    if metadata.writers and not movie.writers:
        updates["writers"] = [p.name for p in metadata.writers]
    if metadata.content_rating and not movie.content_rating:
        updates["content_rating"] = metadata.content_rating
    if metadata.trailer_url and not movie.trailer_url:
        updates["trailer_url"] = metadata.trailer_url
    if metadata.localized:
        localized: dict[str, dict[str, object]] = {}
        for lang, fields in metadata.localized.items():
            loc_entry: dict[str, object] = {}
            if fields.title:
                loc_entry["title"] = fields.title
            if fields.synopsis:
                loc_entry["synopsis"] = fields.synopsis
            if fields.genres:
                loc_entry["genres"] = fields.genres
            if loc_entry:
                localized[lang] = loc_entry
        if localized:
            updates["localized"] = {**movie.localized, **localized}


__all__ = ["EnrichMovieMetadataUseCase"]
