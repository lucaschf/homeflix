"""Use case for enriching a series with external metadata."""

import logging
from datetime import date

from src.building_blocks.application.errors import ResourceNotFoundException
from src.modules.media.application.dtos.enrichment_dtos import (
    EnrichMediaInput,
    EnrichMediaOutput,
)
from src.modules.media.application.ports import (
    EpisodeMetadata,
    MediaMetadata,
    MetadataProvider,
    SeasonMetadata,
)
from src.modules.media.domain.entities import Episode, Season, Series
from src.modules.media.domain.repositories import SeriesRepository
from src.modules.media.domain.value_objects import (
    AirDate,
    Duration,
    Genre,
    ImageUrl,
    ImdbId,
    SeriesId,
    Title,
    TmdbId,
    Year,
)


class EnrichSeriesMetadataUseCase:
    """Enrich a series entity with metadata from external providers.

    Searches the primary provider first, falls back to the secondary.
    Enriches series-level, season-level, and episode-level metadata.

    Args:
        series_repository: Repository for series persistence.
        primary_provider: Primary metadata provider (e.g., TMDB).
        fallback_provider: Optional fallback provider (e.g., OMDb).
    """

    def __init__(
        self,
        series_repository: SeriesRepository,
        primary_provider: MetadataProvider,
        fallback_provider: MetadataProvider | None = None,
    ) -> None:
        self._series_repository = series_repository
        self._primary = primary_provider
        self._fallback = fallback_provider

    async def execute(self, input_dto: EnrichMediaInput) -> EnrichMediaOutput:
        """Execute series metadata enrichment.

        Args:
            input_dto: Input with series ID and force flag.

        Returns:
            Enrichment result with success/failure status.
        """
        series = await self._series_repository.find_by_id(SeriesId(input_dto.media_id))
        if not series:
            raise ResourceNotFoundException.for_resource("Series", input_dto.media_id)

        if series.tmdb_id and not input_dto.force:
            return EnrichMediaOutput(media_id=input_dto.media_id, enriched=False, provider=None)

        metadata, provider_name = await self._fetch_metadata(series)
        if not metadata:
            return EnrichMediaOutput(
                media_id=input_dto.media_id,
                enriched=False,
                error="No metadata found from any provider",
            )

        # Re-fetch with localization if provider supports it
        if metadata.tmdb_id and hasattr(self._primary, "get_series_localized"):
            get_localized = self._primary.get_series_localized
            localized_meta: MediaMetadata | None = await get_localized(metadata.tmdb_id)
            if localized_meta is not None:
                metadata = localized_meta

        series = _apply_series_metadata(series, metadata)
        await self._series_repository.save(series)

        return EnrichMediaOutput(media_id=input_dto.media_id, enriched=True, provider=provider_name)

    async def _fetch_metadata(self, series: Series) -> tuple[MediaMetadata | None, str | None]:
        """Try primary provider, then fallback.

        Searches with original title first, then retries with a
        cleaned title and without year for better TMDB matching.
        """
        if series.tmdb_id:
            metadata = await self._primary.get_series_by_id(series.tmdb_id.value)
            if metadata:
                return metadata, "tmdb"

        title = series.title.value
        year = series.start_year.value

        # Try with original title + year
        metadata = await self._primary.search_series(title, year)
        if metadata:
            return metadata, "tmdb"

        # Retry with cleaned title and no year
        clean = _clean_series_title(title)
        if clean != title:
            metadata = await self._primary.search_series(clean)
            if metadata:
                return metadata, "tmdb"

        # Retry with just title, no year
        metadata = await self._primary.search_series(title)
        if metadata:
            return metadata, "tmdb"

        if self._fallback:
            metadata = await self._fallback.search_series(clean, year)
            if metadata:
                return metadata, "omdb"

        _logger.warning("No metadata found for series %r", title)
        return None, None


def _apply_localized(
    updates: dict[str, object],
    existing: dict[str, dict[str, object]],
    metadata: MediaMetadata,
) -> None:
    """Apply localized metadata overrides from provider."""
    if not metadata.localized:
        return
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
        updates["localized"] = {**existing, **localized}


def _apply_series_metadata(series: Series, metadata: MediaMetadata) -> Series:
    """Apply metadata fields to a series entity."""
    updates: dict[str, object] = {}

    if metadata.synopsis and not series.synopsis:
        updates["synopsis"] = metadata.synopsis
    if metadata.tmdb_id:
        updates["tmdb_id"] = TmdbId(metadata.tmdb_id)
    if metadata.imdb_id:
        updates["imdb_id"] = ImdbId(metadata.imdb_id)
    if metadata.original_title:
        updates["original_title"] = Title(metadata.original_title)
    if metadata.year:
        updates["start_year"] = Year(metadata.year)
    if metadata.end_year:
        updates["end_year"] = Year(metadata.end_year)
    if metadata.genres and not series.genres:
        updates["genres"] = [Genre(g) for g in metadata.genres]
    if metadata.poster_url and not series.poster_path:
        updates["poster_path"] = ImageUrl(metadata.poster_url)
    if metadata.backdrop_url and not series.backdrop_path:
        updates["backdrop_path"] = ImageUrl(metadata.backdrop_url)

    _apply_localized(updates, series.localized, metadata)

    if updates:
        series = series.with_updates(**updates)

    # Enrich seasons and episodes
    if metadata.seasons:
        series = _enrich_seasons(series, metadata.seasons)

    return series


def _enrich_seasons(series: Series, season_metas: list[SeasonMetadata]) -> Series:
    """Enrich existing seasons with metadata."""
    meta_by_num = {s.season_number: s for s in season_metas}

    new_seasons = []
    for season in series.seasons:
        meta = meta_by_num.get(season.season_number)
        enriched = _apply_season_metadata(season, meta) if meta else season
        new_seasons.append(enriched)

    return series.with_updates(seasons=new_seasons)


def _apply_season_metadata(season: Season, meta: SeasonMetadata) -> Season:
    """Apply metadata to a season and its episodes."""
    updates: dict[str, object] = {}

    if meta.title and not season.title:
        updates["title"] = Title(meta.title)
    if meta.synopsis and not season.synopsis:
        updates["synopsis"] = meta.synopsis
    if meta.air_date and not season.air_date:
        parsed = _parse_date(meta.air_date)
        if parsed:
            updates["air_date"] = AirDate(parsed)

    if updates:
        season = season.with_updates(**updates)

    # Enrich episodes
    if meta.episodes:
        ep_by_num = {e.episode_number: e for e in meta.episodes}
        new_episodes = []
        for ep in season.episodes:
            ep_meta = ep_by_num.get(ep.episode_number)
            enriched_ep = _apply_episode_metadata(ep, ep_meta) if ep_meta else ep
            new_episodes.append(enriched_ep)
        season = season.with_updates(episodes=new_episodes)

    return season


def _apply_episode_metadata(episode: Episode, meta: EpisodeMetadata) -> Episode:
    """Apply metadata to an episode."""
    updates: dict[str, object] = {}

    if meta.title and episode.title.value.startswith("Episode "):
        updates["title"] = Title(meta.title)
    if meta.synopsis and not episode.synopsis:
        updates["synopsis"] = meta.synopsis
    if meta.air_date and not episode.air_date:
        parsed = _parse_date(meta.air_date)
        if parsed:
            updates["air_date"] = AirDate(parsed)
    if meta.duration_seconds and episode.duration.value == 0:
        updates["duration"] = Duration(meta.duration_seconds)
    if meta.still_url and not episode.thumbnail_path:
        updates["thumbnail_path"] = ImageUrl(meta.still_url)

    if updates:
        episode = episode.with_updates(**updates)

    return episode


_logger = logging.getLogger(__name__)


def _clean_series_title(title: str) -> str:
    """Remove common noise from a series title for better TMDB search."""
    import re

    patterns = [
        r"\b(?:4K|UHD|FHD|HD|SD)\b",
        r"\b(?:BluRay|BDRip|BRRip|WEB-?DL|WEB-?Rip|HDTV|DVDRip|REMUX)\b",
        r"\b(?:HEVC|H\.?265|H\.?264|x264|x265|AV1|VP9|MPEG4)\b",
        r"\b(?:DTS(?:-HD)?(?:\.?MA)?|TrueHD|Atmos|AAC|AC3|FLAC|EAC3)\b",
        r"\[.*?\]",
        r"\(.*?\)",
    ]
    result = title
    for pattern in patterns:
        result = re.sub(pattern, "", result, flags=re.IGNORECASE)

    result = re.sub(r"\s+", " ", result).strip().strip("-._")
    return result or title


def _parse_date(value: str) -> date | None:
    """Safely parse an ISO date string, returning None on failure."""
    try:
        return date.fromisoformat(value)
    except ValueError:
        _logger.warning("Could not parse date: %s", value)
        return None


__all__ = ["EnrichSeriesMetadataUseCase"]
