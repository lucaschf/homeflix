"""Use case for enriching a movie with external metadata."""

import logging

from src.building_blocks.application.errors import ResourceNotFoundException
from src.building_blocks.application.event_bus import EventBus
from src.modules.media.application.dtos.enrichment_dtos import (
    EnrichMediaInput,
    EnrichMediaOutput,
)
from src.modules.media.application.ports import MediaMetadata, MetadataProvider
from src.modules.media.application.unit_of_work import MediaUnitOfWorkFactory
from src.modules.media.application.use_cases._localized_metadata_helpers import (
    merge_localized_metadata,
)
from src.modules.media.domain.entities import Movie
from src.modules.media.domain.events import MediaEnrichedEvent
from src.modules.media.domain.value_objects import (
    CastMember,
    Collection,
    ContentRating,
    Duration,
    Genre,
    ImageUrl,
    ImdbId,
    MovieId,
    Title,
    TmdbId,
    Year,
)
from src.shared_kernel.value_objects.media_type import MediaType

_logger = logging.getLogger(__name__)


class EnrichMovieMetadataUseCase:
    """Enrich a movie entity with metadata from external providers.

    Searches the primary provider first, falls back to the secondary
    if the primary returns no results.

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
        """Execute movie metadata enrichment.

        Args:
            input_dto: Input with movie ID and force flag.

        Returns:
            Enrichment result with success/failure status.
        """
        async with self._uow_factory() as uow:
            movie = await uow.movies.find_by_id(MovieId(input_dto.media_id))
            if not movie:
                raise ResourceNotFoundException.for_resource("Movie", input_dto.media_id)

            if movie.tmdb_id and not input_dto.force:
                return EnrichMediaOutput(media_id=input_dto.media_id, enriched=False, provider=None)

            metadata, provider_name = await self._fetch_metadata(movie)
            if not metadata:
                error_msg = await self._build_no_metadata_error(movie, input_dto.media_id)
                # Flag the movie for admin review (cleared on the next
                # successful enrichment). Persisting on the failure
                # path turns "log-only cross-type hints" into a
                # queryable inbox.
                if not movie.needs_enrichment_review:
                    movie = movie.with_updates(needs_enrichment_review=True)
                    await uow.movies.save(movie)
                return EnrichMediaOutput(
                    media_id=input_dto.media_id,
                    enriched=False,
                    error=error_msg,
                )

            # Re-fetch with localization if TMDB provider supports it
            if metadata.tmdb_id and hasattr(self._primary, "get_movie_localized"):
                get_localized = self._primary.get_movie_localized
                localized_meta: MediaMetadata | None = await get_localized(metadata.tmdb_id)
                if localized_meta is not None:
                    metadata = localized_meta

            movie = _apply_movie_metadata(movie, metadata, force=input_dto.force)
            if movie.needs_enrichment_review:
                movie = movie.with_updates(needs_enrichment_review=False)
            await uow.movies.save(movie)
            enriched_tmdb_id = movie.tmdb_id.value if movie.tmdb_id else None

        # Publish outside the UoW so a slow handler doesn't hold the
        # write transaction open. ``catalog_requests`` listens for
        # this event to flip pending requests to fulfilled.
        if enriched_tmdb_id is not None and self._event_bus is not None:
            await self._event_bus.publish(
                MediaEnrichedEvent(
                    media_id=MovieId(input_dto.media_id),
                    media_type=MediaType.MOVIE,
                    tmdb_id=enriched_tmdb_id,
                ),
            )

        return EnrichMediaOutput(media_id=input_dto.media_id, enriched=True, provider=provider_name)

    async def _fetch_metadata(self, movie: Movie) -> tuple[MediaMetadata | None, str | None]:
        """Try primary provider, then fallback.

        Always year-strict: every search retains the ``year`` hint so a
        popular off-year title (e.g. ``Salem's Lot`` 2024 outranking the
        1979 entry that doesn't exist as a movie on TMDB at all) cannot
        win as a silent title-only fallback. When no year-correct match
        is found, ``_build_no_metadata_error`` runs a cross-type check
        against ``/search/tv`` so the user gets an actionable hint
        instead of a wrong enrichment.
        """
        if movie.tmdb_id:
            metadata = await self._primary.get_movie_by_id(movie.tmdb_id.value)
            if metadata:
                return metadata, "tmdb"

        title = movie.title.value
        year = movie.year.value

        metadata = await self._primary.search_movie(title, year)
        if metadata:
            return metadata, "tmdb"

        # Retry with quality tags stripped — keep the year hint so we
        # don't open the door to off-year matches the strict search
        # already rejected.
        clean = _clean_title(title)
        if clean != title:
            metadata = await self._primary.search_movie(clean, year)
            if metadata:
                return metadata, "tmdb"

        if self._fallback:
            metadata = await self._fallback.search_movie(clean or title, year)
            if metadata:
                return metadata, "omdb"

        _logger.warning("No metadata found for movie %r (year=%s)", title, year)
        return None, None

    async def _detect_cross_type_series(self, title: str, year: int | None) -> int | None:
        """Look for a TV series match when a movie search came back empty.

        Why: the scanner classifies any file without an ``SxxExx`` pattern
        as a Movie (see ``scanner.py:_detect_episode``), but some titles
        only exist on TMDB as TV miniseries — e.g. ``Salem's Lot (1979)``
        lives at ``tmdb/tv/16118``, not under ``/search/movie`` at all.
        When the movie path can't find a match, we re-query ``/search/tv``
        so we can surface an actionable hint instead of silently leaving
        the item un-enriched. Returns the TMDB series ID on match, or
        ``None`` if the title isn't on the TV side either.
        """
        metadata = await self._primary.search_series(title, year)
        if metadata is None and year is not None:
            metadata = await self._primary.search_series(title)
        return metadata.tmdb_id if metadata else None

    async def _build_no_metadata_error(self, movie: Movie, media_id: str) -> str:
        """Produce the ``error`` payload for a failed enrichment.

        Defaults to a generic "no provider matched" message. When the
        title resolves on the TV side instead, the message embeds the
        suggested TMDB series ID so the user can re-classify the file
        (move into a series library or rename with ``SxxExx``).
        """
        cross_type_tmdb_id = await self._detect_cross_type_series(
            movie.title.value, movie.year.value
        )
        if cross_type_tmdb_id is None:
            return "No metadata found from any provider"

        _logger.warning(
            "Cross-type match for movie %r (id=%s): TMDB series tv/%s",
            movie.title.value,
            media_id,
            cross_type_tmdb_id,
        )
        return (
            f"Cross-type match: this title appears to be a TV series on TMDB "
            f"(tmdb/tv/{cross_type_tmdb_id}). Move the file into a series "
            f"library or rename with an SxxExx pattern so the scanner "
            f"classifies it as a series."
        )


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


def _apply_movie_metadata(
    movie: Movie,
    metadata: MediaMetadata,
    *,
    force: bool = False,
) -> Movie:
    """Apply metadata fields to a movie entity.

    Each field has a "fill if empty" guard by default so re-enrichment
    doesn't clobber user customizations (a synopsis the user edited,
    a poster they picked manually, etc.). When ``force=True`` every
    guard is bypassed and TMDB's payload wins — used by the bulk
    enrich's "force update" toggle to backfill new fields (like the
    cast member ``tmdb_id``) on rows that were already enriched.
    """
    updates: dict[str, object] = {}

    if metadata.title:
        updates["title"] = Title(metadata.title)
    if metadata.synopsis and (force or not movie.synopsis):
        updates["synopsis"] = metadata.synopsis
    _apply_franchise_metadata(updates, movie, metadata, force=force)
    if metadata.tmdb_id:
        updates["tmdb_id"] = TmdbId(metadata.tmdb_id)
    if metadata.imdb_id:
        updates["imdb_id"] = ImdbId(metadata.imdb_id)
    if metadata.original_title:
        updates["original_title"] = Title(metadata.original_title)
    if metadata.duration_seconds and (force or movie.duration.value == 0):
        updates["duration"] = Duration(metadata.duration_seconds)
    if metadata.year:
        updates["year"] = Year(metadata.year)
    if metadata.genres and (force or not movie.genres):
        updates["genres"] = [Genre(g) for g in metadata.genres]
    if metadata.poster_url and (force or not movie.poster_path):
        updates["poster_path"] = ImageUrl(metadata.poster_url)
    if metadata.backdrop_url and (force or not movie.backdrop_path):
        updates["backdrop_path"] = ImageUrl(metadata.backdrop_url)
    if metadata.logo_url and (force or not movie.logo_path):
        updates["logo_path"] = ImageUrl(metadata.logo_url)

    _apply_credits(updates, movie, metadata, force=force)

    if updates:
        movie = movie.with_updates(**updates)

    return movie


def _apply_franchise_metadata(
    updates: dict[str, object],
    movie: Movie,
    metadata: MediaMetadata,
    *,
    force: bool = False,
) -> None:
    """Apply tagline + collection (franchise) metadata.

    Both fields follow the same "fill if empty" guard as the rest of
    ``_apply_movie_metadata`` so re-enrichment doesn't clobber a
    user-edited tagline or a manually-cleared collection. Extracted
    out so the parent function stays under ``PLR0912``'s branch cap.
    """
    if metadata.tagline and (force or not movie.tagline):
        updates["tagline"] = metadata.tagline
    if metadata.collection and (force or not movie.collection):
        updates["collection"] = Collection(
            tmdb_id=metadata.collection.tmdb_id,
            name=metadata.collection.name,
            parts_count=metadata.collection.parts_count,
        )


def _apply_credits(
    updates: dict[str, object],
    movie: Movie,
    metadata: MediaMetadata,
    *,
    force: bool = False,
) -> None:
    """Apply cast/director/writer credits.

    Each field defaults to a "fill if empty" guard; ``force=True``
    bypasses the guard so a refresh repopulates credits from TMDB.
    The motivating use case is backfilling ``tmdb_id`` on cast
    members that were already saved before the id was captured.
    """
    if metadata.cast and (force or not movie.cast):
        updates["cast"] = [
            CastMember(
                name=p.name,
                profile_path=p.profile_url,
                role=p.role,
                tmdb_id=p.tmdb_id,
            )
            for p in metadata.cast
        ]
    if metadata.directors and (force or not movie.directors):
        updates["directors"] = [p.name for p in metadata.directors]
    if metadata.writers and (force or not movie.writers):
        updates["writers"] = [p.name for p in metadata.writers]
    if metadata.content_rating and (force or not movie.content_rating):
        updates["content_rating"] = ContentRating(metadata.content_rating)
    if metadata.trailer_url and (force or not movie.trailer_url):
        updates["trailer_url"] = metadata.trailer_url
    merge_localized_metadata(updates, movie.localized, metadata)


__all__ = ["EnrichMovieMetadataUseCase"]
