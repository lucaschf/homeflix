"""Use case for enriching a series with external metadata."""

import logging
from collections.abc import Callable
from datetime import date
from typing import Any

from src.building_blocks.application.errors import ResourceNotFoundException
from src.building_blocks.application.event_bus import EventBus
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
from src.modules.media.application.unit_of_work import MediaUnitOfWorkFactory
from src.modules.media.application.use_cases._localized_metadata_helpers import (
    merge_media_localized,
    merge_text_localized,
)
from src.modules.media.domain.entities import Episode, Season, Series
from src.modules.media.domain.value_objects import (
    AirDate,
    CastMember,
    ContentRating,
    Duration,
    Genre,
    ImageUrl,
    ImdbId,
    LocalizedFields,
    LocalizedMetadata,
    MergePolicy,
    SeriesId,
    Title,
    TmdbId,
    Year,
)
from src.shared_kernel.integration_events import MediaEnrichedEvent
from src.shared_kernel.value_objects.media_type import MediaType


class EnrichSeriesMetadataUseCase:
    """Enrich a series entity with metadata from external providers.

    Searches the primary provider first, falls back to the secondary.
    Enriches series-level, season-level, and episode-level metadata.

    Args:
        uow_factory: Factory that opens a fresh media Unit of Work.
        primary_provider: Primary metadata provider (e.g., TMDB).
        fallback_provider: Optional fallback provider (e.g., OMDb).
    """

    def __init__(
        self,
        uow_factory: MediaUnitOfWorkFactory,
        primary_provider: MetadataProvider,
        fallback_provider: MetadataProvider | None = None,
        event_bus: EventBus | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._primary = primary_provider
        self._fallback = fallback_provider
        self._event_bus = event_bus

    async def execute(self, input_dto: EnrichMediaInput) -> EnrichMediaOutput:
        """Execute series metadata enrichment.

        Args:
            input_dto: Input with series ID and force flag.

        Returns:
            Enrichment result with success/failure status.
        """
        async with self._uow_factory() as uow:
            series = await uow.series.find_by_id(SeriesId(input_dto.media_id))
            if not series:
                raise ResourceNotFoundException.for_resource("Series", input_dto.media_id)

            if series.tmdb_id and not input_dto.force:
                return EnrichMediaOutput(media_id=input_dto.media_id, enriched=False, provider=None)

            metadata, provider_name = await self._fetch_metadata(series)
            if not metadata:
                # Flag for admin review (cleared on the next successful
                # enrichment) so the unresolved series surfaces on the
                # needs-review queue instead of silently staying bare.
                if not series.needs_enrichment_review:
                    series = series.with_enrichment_review_flagged()
                    await uow.series.save(series)
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

            series = _apply_series_metadata(
                series, metadata, policy=MergePolicy.from_force(input_dto.force)
            )
            if series.needs_enrichment_review:
                series = series.with_updates(needs_enrichment_review=False)
            await uow.series.save(series)
            enriched_tmdb_id = series.tmdb_id.value if series.tmdb_id else None

        # Publish outside the UoW so a slow handler doesn't hold the
        # write transaction open. ``catalog_requests`` listens for
        # this event to flip pending requests to fulfilled.
        if enriched_tmdb_id is not None and self._event_bus is not None:
            await self._event_bus.publish(
                MediaEnrichedEvent(
                    media_id=SeriesId(input_dto.media_id),
                    media_type=MediaType.SERIES,
                    tmdb_id=enriched_tmdb_id,
                ),
            )

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


def _set_if_missing(
    updates: dict[str, object],
    metadata: MediaMetadata,
    entity: Series,
    field_map: dict[str, tuple[str, Callable[[Any], Any] | None]],
    *,
    policy: MergePolicy = MergePolicy.FILL_IF_EMPTY,
) -> None:
    """Set fields in updates, respecting the merge policy.

    A field is written when metadata has a value and ``policy.should_write``
    allows it (always under ``OVERWRITE``; only when the entity field is
    empty under ``FILL_IF_EMPTY``). The fill-if-empty guard protects user
    edits on a routine re-enrichment; ``OVERWRITE`` (a relink / forced
    refresh) bypasses it so metadata from the newly-picked match overwrites
    stale values left by a wrong match.
    """
    for meta_attr, (entity_attr, converter) in field_map.items():
        meta_val = getattr(metadata, meta_attr, None)
        entity_val = getattr(entity, entity_attr, None)
        if meta_val and policy.should_write(entity_val):
            updates[entity_attr] = converter(meta_val) if converter is not None else meta_val


def _apply_series_metadata(
    series: Series,
    metadata: MediaMetadata,
    *,
    policy: MergePolicy = MergePolicy.FILL_IF_EMPTY,
) -> Series:
    """Apply metadata fields to a series entity.

    Each "don't-overwrite" field has a fill-if-empty guard by default so
    a routine re-enrichment doesn't clobber user edits. Under
    ``MergePolicy.OVERWRITE`` (a relink, where the existing data belongs to
    a wrong match) every guard is bypassed and the provider payload wins —
    including a full replace of the ``localized`` overrides and the base title.
    """
    updates: dict[str, object] = {}

    # Always-overwrite fields
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
    elif policy.overwrites:
        # On a relink the new match may be ongoing (no end_year) while a
        # stale end_year lingers from the wrong match. Left in place it
        # can fall before the new start_year and trip the
        # ``end_year >= start_year`` invariant — clear it.
        updates["end_year"] = None
    # The base title normally stays scanner-derived, but on a forced
    # refresh it may belong to a wrong match — overwrite it so the
    # canonical title tracks the newly-picked TMDB entry.
    if metadata.title and policy.overwrites:
        updates["title"] = Title(metadata.title)

    # Don't-overwrite fields (only set if empty, unless ``OVERWRITE``)
    _set_if_missing(
        updates,
        metadata,
        series,
        {
            "synopsis": ("synopsis", None),
            "genres": ("genres", lambda v: [Genre(g) for g in v]),
            "poster_url": ("poster_path", ImageUrl),
            "backdrop_url": ("backdrop_path", ImageUrl),
            "logo_url": ("logo_path", ImageUrl),
            "content_rating": ("content_rating", ContentRating),
            "trailer_url": ("trailer_url", None),
        },
        policy=policy,
    )

    # Cast: same fill-if-empty rule as the rest of the don't-overwrite
    # block, but built outside ``_set_if_missing`` because the
    # provider DTO uses a different field name (``cast`` ↔ ``cast``)
    # AND a per-element converter from ``CreditPerson`` to the
    # domain ``CastMember`` VO.
    if metadata.cast and policy.should_write(series.cast):
        updates["cast"] = [
            CastMember(
                name=p.name,
                profile_path=p.profile_url,
                role=p.role,
                tmdb_id=p.tmdb_id,
            )
            for p in metadata.cast
        ]

    new_localized = merge_media_localized(series.localized, metadata, policy=policy)
    if new_localized is not None:
        updates["localized"] = new_localized

    if updates:
        series = series.with_updates(**updates)

    # Enrich seasons and episodes
    if metadata.seasons:
        series = _enrich_seasons(series, metadata.seasons, policy=policy)

    return series


def _enrich_seasons(
    series: Series,
    season_metas: list[SeasonMetadata],
    *,
    policy: MergePolicy = MergePolicy.FILL_IF_EMPTY,
) -> Series:
    """Enrich existing seasons with metadata."""
    meta_by_num = {s.season_number: s for s in season_metas}  # int keys from API

    new_seasons = []
    for season in series.seasons:
        meta = meta_by_num.get(season.season_number.value)
        enriched = _apply_season_metadata(season, meta, policy=policy) if meta else season
        new_seasons.append(enriched)

    return series.with_updates(seasons=new_seasons)


def _apply_season_metadata(
    season: Season, meta: SeasonMetadata, *, policy: MergePolicy = MergePolicy.FILL_IF_EMPTY
) -> Season:
    """Apply metadata to a season and its episodes."""
    updates: dict[str, object] = {}

    if meta.title and policy.should_write(season.title):
        updates["title"] = Title(meta.title)
    if meta.synopsis and policy.should_write(season.synopsis):
        updates["synopsis"] = meta.synopsis
    if meta.air_date and policy.should_write(season.air_date):
        parsed = _parse_date(meta.air_date)
        if parsed:
            updates["air_date"] = AirDate(parsed)
    season_localized = merge_text_localized(season.localized, meta.localized, policy=policy)
    if season_localized is not None:
        updates["localized"] = season_localized

    if updates:
        season = season.with_updates(**updates)

    # Enrich episodes — track TMDB index separately to handle multi-segment files
    if meta.episodes:
        ep_by_num = {e.episode_number: e for e in meta.episodes}  # int keys from API
        sorted_episodes = sorted(season.episodes, key=lambda e: e.episode_number.value)
        tmdb_idx = 1  # TMDB episode numbering starts at 1
        new_episodes = []
        for ep in sorted_episodes:
            segment_count = _detect_multi_episode(ep.title.value)
            if segment_count > 1:
                enriched_ep = _apply_multi_episode_metadata(
                    ep, ep_by_num, segment_count, tmdb_start=tmdb_idx, policy=policy
                )
            else:
                ep_meta = ep_by_num.get(tmdb_idx)
                enriched_ep = _apply_episode_metadata(ep, ep_meta, policy=policy) if ep_meta else ep
            new_episodes.append(enriched_ep)
            tmdb_idx += segment_count
        season = season.with_updates(episodes=new_episodes)

    return season


def _detect_multi_episode(title: str) -> int:
    """Detect how many episodes are in a single file based on title.

    Counts segments separated by `` - `` in the episode title.
    Titles like "Downtown as Fruits - Eugene's Bike" have 2 segments.

    Returns:
        Number of episodes detected (1 = single, 2+ = multi).
    """
    # Skip titles that are just generic "Episode N" from the scanner
    if title.startswith("Episode "):
        return 1
    parts = [p.strip() for p in title.split(" - ") if p.strip()]
    # Cap at 4 to avoid false positives from stylized titles
    return min(max(len(parts), 1), 4)


def _apply_multi_episode_metadata(
    episode: Episode,
    ep_by_num: dict[int, EpisodeMetadata],
    segment_count: int,
    tmdb_start: int | None = None,
    *,
    policy: MergePolicy = MergePolicy.FILL_IF_EMPTY,
) -> Episode:
    """Apply combined metadata from multiple TMDB episodes to a multi-segment file.

    Concatenates titles with ``/``, joins synopses, sums durations,
    and uses the first episode's thumbnail.

    Args:
        episode: The local episode entity.
        ep_by_num: TMDB episodes keyed by episode number.
        segment_count: Number of TMDB episodes in this file.
        tmdb_start: Starting TMDB episode number (if None, uses episode.episode_number).
        policy: ``OVERWRITE`` (a relink) bypasses the fill-if-empty guards
            so a wrong match's episode data is replaced.
    """
    start = tmdb_start if tmdb_start is not None else episode.episode_number.value
    metas = [ep_by_num.get(start + i) for i in range(segment_count)]
    present = [m for m in metas if m is not None]

    if not present:
        return episode

    updates: dict[str, object] = {}

    # Concatenate titles from all segments (only if local title is from
    # scanner, or on a forced refresh where the stored title may be wrong)
    titles = [m.title for m in present if m.title]
    if titles and (policy.overwrites or " / " not in episode.title.value):
        updates["title"] = Title(" / ".join(titles))

    # Synopsis: combine with separator
    synopses = [m.synopsis for m in present if m.synopsis]
    if synopses and policy.should_write(episode.synopsis):
        updates["synopsis"] = " ◆ ".join(synopses)

    # Sum durations from all segments. Only a fallback — the scanner
    # stamps the file's real probed duration; never overwrite it (even on
    # OVERWRITE) with TMDB's nominal runtime.
    total_duration = sum(m.duration_seconds or 0 for m in present)
    if total_duration and episode.duration.value == 0:
        updates["duration"] = Duration(total_duration)

    # Thumbnail: first available
    first_still = next((m.still_url for m in present if m.still_url), None)
    if first_still and policy.should_write(episode.thumbnail_path):
        updates["thumbnail_path"] = ImageUrl(first_still)

    # Air date: first available
    first_date = next((m.air_date for m in present if m.air_date), None)
    if first_date and policy.should_write(episode.air_date):
        parsed = _parse_date(first_date)
        if parsed:
            updates["air_date"] = AirDate(parsed)

    combined_localized = _combine_localized_segments(present, episode.localized, policy=policy)
    if combined_localized is not None:
        updates["localized"] = combined_localized

    if updates:
        episode = episode.with_updates(**updates)

    return episode


def _combine_localized_segments(
    present: list[EpisodeMetadata],
    existing: LocalizedMetadata,
    *,
    policy: MergePolicy,
) -> LocalizedMetadata | None:
    """Combine per-locale title/synopsis across a multi-segment file's episodes.

    Mirrors the English combine (titles joined with `` / ``, synopses
    with `` ◆ ``) per locale so a translated multi-segment file keeps
    its localized text. Returns ``None`` when no locale has data; otherwise
    replaces (``OVERWRITE``) or merges the combined overrides over ``existing``.
    """
    locales = {loc for m in present for loc in m.localized}
    by_locale: dict[str, LocalizedFields] = {}
    for loc in locales:
        segments = [m.localized[loc] for m in present if loc in m.localized]
        titles = [s.title for s in segments if s.title]
        synopses = [s.synopsis for s in segments if s.synopsis]
        fields = LocalizedFields(
            title=" / ".join(titles) if titles else None,
            synopsis=" ◆ ".join(synopses) if synopses else None,
        )
        if not fields.is_empty():
            by_locale[loc] = fields

    if not by_locale:
        return None

    combined = LocalizedMetadata(by_locale)
    return combined if policy.overwrites else existing.merge(combined)


def _apply_episode_metadata(
    episode: Episode, meta: EpisodeMetadata, *, policy: MergePolicy = MergePolicy.FILL_IF_EMPTY
) -> Episode:
    """Apply metadata from a single TMDB episode.

    Each field is fill-if-empty by default (and the title only replaces
    a generic scanner ``Episode N`` placeholder). ``MergePolicy.OVERWRITE``
    (a relink) bypasses both guards so a wrong match's episode data is replaced.
    """
    updates: dict[str, object] = {}

    if meta.title and (
        policy.overwrites or episode.title.value.startswith("Episode ")
    ):
        updates["title"] = Title(meta.title)
    if meta.synopsis and policy.should_write(episode.synopsis):
        updates["synopsis"] = meta.synopsis
    if meta.air_date and policy.should_write(episode.air_date):
        parsed = _parse_date(meta.air_date)
        if parsed:
            updates["air_date"] = AirDate(parsed)
    # Fallback only — real duration comes from the file probe at scan time.
    if meta.duration_seconds and episode.duration.value == 0:
        updates["duration"] = Duration(meta.duration_seconds)
    if meta.still_url and policy.should_write(episode.thumbnail_path):
        updates["thumbnail_path"] = ImageUrl(meta.still_url)
    episode_localized = merge_text_localized(episode.localized, meta.localized, policy=policy)
    if episode_localized is not None:
        updates["localized"] = episode_localized

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
