"""Use case: convert a Movie into a Series (Salem's Lot case)."""

import logging

from src.building_blocks.application.errors import (
    ResourceNotFoundException,
    UseCaseValidationException,
)
from src.building_blocks.application.event_bus import EventBus
from src.modules.media.application.dtos.admin_relink_dtos import (
    PromoteMovieToSeriesInput,
    PromoteMovieToSeriesOutput,
)
from src.modules.media.application.dtos.enrichment_dtos import EnrichMediaInput
from src.modules.media.application.ports import MediaMetadata, MetadataProvider
from src.modules.media.application.unit_of_work import MediaUnitOfWorkFactory
from src.modules.media.application.use_cases.enrich_series_metadata import (
    EnrichSeriesMetadataUseCase,
)
from src.modules.media.domain.entities import Episode, Movie, Season, Series
from src.modules.media.domain.value_objects import (
    Duration,
    EpisodeId,
    EpisodeNumber,
    MovieId,
    SeasonId,
    SeasonNumber,
    SeriesId,
    Title,
    TmdbId,
    Year,
)
from src.shared_kernel.integration_events import MoviePromotedToSeriesEvent

_logger = logging.getLogger(__name__)


class PromoteMovieToSeriesUseCase:
    """Convert a misclassified Movie into a Series.

    Driven by ``Salem's Lot (1979)``-style cases: TMDB catalogs the
    title as a TV miniseries (``/tv/16118``) but the scanner — which
    classifies by filename pattern — registered it as a Movie. The
    flow:

        1. Fetch TMDB series details by id (validates that the
           supplied id really is a series; aborts early on miss).
        2. Build ``Series + Season(1) + N episodes`` (where ``N`` is
           the TMDB season's episode count, clamped to ``>= 1``).
        3. Save the structure, then re-FK every ``media_files`` row
           from the source movie to the first episode (file path
           UNIQUE-ness rules out creating fresh rows).
        4. Soft-delete the source movie.
        5. Publish ``MoviePromotedToSeriesEvent`` so cross-BC
           handlers can clear stale ``watch_progresses`` rows and
           rewrite ``watchlist`` / ``custom_list`` refs.
        6. Trigger ``EnrichSeriesMetadataUseCase`` to backfill the
           episode-level metadata (air dates, synopses, thumbnails)
           that TMDB already has.

    The re-enrich step runs *after* commit so a transient TMDB
    failure doesn't roll the whole promotion back — admin can hit
    the regular enrich endpoint to retry just that piece.

    Args:
        uow_factory: Factory that opens a fresh media Unit of Work.
        metadata_provider: Metadata port used to fetch the TMDB
            series shape (episode count, season metadata).
        enrich_series_use_case: Series enrichment to run after the
            structure is in place.
        event_bus: Event bus used to publish
            ``MoviePromotedToSeriesEvent``.
    """

    def __init__(
        self,
        uow_factory: MediaUnitOfWorkFactory,
        metadata_provider: MetadataProvider,
        enrich_series_use_case: EnrichSeriesMetadataUseCase,
        event_bus: EventBus,
    ) -> None:
        self._uow_factory = uow_factory
        self._metadata_provider = metadata_provider
        self._enrich_series = enrich_series_use_case
        self._event_bus = event_bus

    async def execute(
        self,
        input_dto: PromoteMovieToSeriesInput,
    ) -> PromoteMovieToSeriesOutput:
        """Execute the promotion."""
        if input_dto.tmdb_id <= 0:
            raise UseCaseValidationException(
                message="tmdb_id must be a positive integer",
                message_code="INVALID_TMDB_ID",
            )

        # Validate the TMDB id up-front, before touching the DB.
        tmdb_meta = await self._metadata_provider.get_series_by_id(input_dto.tmdb_id)
        if tmdb_meta is None:
            raise ResourceNotFoundException.for_resource("TmdbSeries", str(input_dto.tmdb_id))

        series_id, first_episode_id, episodes_count = await self._run_conversion(
            input_dto, tmdb_meta
        )

        # Cross-BC fan-out runs after the catalog mutation commits so
        # handlers observe the post-promote state.
        await self._event_bus.publish(
            MoviePromotedToSeriesEvent(
                movie_id=MovieId(input_dto.movie_id),
                series_id=SeriesId(series_id),
                first_episode_id=EpisodeId(first_episode_id),
            ),
        )

        # Best-effort metadata backfill — the structure is already
        # correct, this just populates titles/dates/thumbs per episode.
        # Swallowed exceptions are visible in the log and retryable
        # via the existing /series/{id}/enrich endpoint.
        try:
            await self._enrich_series.execute(
                EnrichMediaInput(media_id=series_id, force=True),
            )
        except Exception:
            _logger.exception(
                "Re-enrich after promotion failed for series %s; "
                "admin can retry via /series/{id}/enrich",
                series_id,
            )

        return PromoteMovieToSeriesOutput(
            movie_id=input_dto.movie_id,
            series_id=series_id,
            first_episode_id=first_episode_id,
            episodes_created=episodes_count,
        )

    async def _run_conversion(
        self,
        input_dto: PromoteMovieToSeriesInput,
        tmdb_meta: MediaMetadata,
    ) -> tuple[str, str, int]:
        """Build + persist the series, move files, soft-delete the movie.

        Returns ``(series_id, first_episode_id, episodes_count)``.
        """
        async with self._uow_factory() as uow:
            movie = await uow.movies.find_by_id(MovieId(input_dto.movie_id))
            if movie is None:
                raise ResourceNotFoundException.for_resource("Movie", input_dto.movie_id)

            series, first_episode_id = _build_series_from_movie(movie, tmdb_meta, input_dto.tmdb_id)
            await uow.series.save(series)

            # Re-FK the existing media_files rows onto the new
            # episode. Reusing rows side-steps the UNIQUE(file_path)
            # constraint and preserves probe-side track metadata.
            moved = await uow.movies.transfer_file_variants_to_episode(
                MovieId(input_dto.movie_id), EpisodeId(first_episode_id)
            )
            _logger.info(
                "Promoted movie %s → series %s, moved %d file variant(s)",
                input_dto.movie_id,
                series.id,
                moved,
            )

            await uow.movies.delete(MovieId(input_dto.movie_id))

            episodes_count = len(series.seasons[0].episodes)

        return str(series.id), first_episode_id, episodes_count


def _build_series_from_movie(
    movie: Movie,
    tmdb_meta: MediaMetadata,
    tmdb_id: int,
) -> tuple[Series, str]:
    """Construct the new Series aggregate without files.

    Episodes are created with empty ``files`` lists; the use case
    re-FKs the existing ``media_files`` rows directly onto the first
    episode after persisting (see ``transfer_file_variants_to_episode``).

    Returns the Series plus the external id of the first episode so
    the caller can route the file relocation + event publish without
    walking the aggregate again.
    """
    first_season = tmdb_meta.seasons[0] if tmdb_meta.seasons else None
    season_number_val = first_season.season_number if first_season else 1
    season_number = SeasonNumber(season_number_val)

    # Default to "1 placeholder episode" if TMDB returned no episodes
    # for this season — keeps the structure consistent so the file
    # always has somewhere to land.
    episode_metas = list(first_season.episodes) if first_season and first_season.episodes else []

    series_id = SeriesId.generate()
    episodes: list[Episode] = []

    if not episode_metas:
        first_episode_id = EpisodeId.generate()
        episodes.append(
            Episode(
                id=first_episode_id,
                series_id=series_id,
                season_number=season_number,
                episode_number=EpisodeNumber(1),
                title=Title("Episode 1"),
                duration=Duration(movie.duration.value),
            )
        )
    else:
        for idx, ep_meta in enumerate(episode_metas):
            episode_id = EpisodeId.generate()
            ep_title = ep_meta.title or f"Episode {ep_meta.episode_number}"
            # First episode inherits the movie's duration so the
            # player has a sane number until TMDB enrichment refreshes
            # it; later episodes start at 0 (TMDB will fill them in).
            ep_duration_seconds = ep_meta.duration_seconds or (
                movie.duration.value if idx == 0 else 0
            )
            episodes.append(
                Episode(
                    id=episode_id,
                    series_id=series_id,
                    season_number=season_number,
                    episode_number=EpisodeNumber(ep_meta.episode_number),
                    title=Title(ep_title),
                    duration=Duration(ep_duration_seconds),
                )
            )

    first_episode_id_str = str(episodes[0].id)

    season = Season(
        id=SeasonId.generate(),
        series_id=series_id,
        season_number=season_number,
        title=Title(first_season.title) if first_season and first_season.title else None,
        air_date=None,
        episodes=episodes,
    )

    series = Series(
        id=series_id,
        library_id=movie.library_id,
        title=Title(tmdb_meta.title or movie.title.value),
        start_year=Year(tmdb_meta.year or movie.year.value),
        tmdb_id=TmdbId(tmdb_id),
        seasons=[season],
    )

    return series, first_episode_id_str


__all__ = ["PromoteMovieToSeriesUseCase"]
