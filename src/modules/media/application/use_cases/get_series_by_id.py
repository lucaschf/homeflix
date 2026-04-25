"""GetSeriesByIdUseCase - Retrieve a series with all seasons and episodes."""

from src.building_blocks.application.errors import ResourceNotFoundException
from src.modules.media.application.dtos.series_dtos import (
    EpisodeOutput,
    GetSeriesByIdInput,
    SeasonOutput,
    SeriesOutput,
)
from src.modules.media.application.ports import ProgressLookupPort, ProgressSummary
from src.modules.media.application.unit_of_work import MediaUnitOfWorkFactory
from src.modules.media.application.use_cases._media_file_helpers import (
    to_media_file_output,
)
from src.modules.media.domain.entities import Episode, Season, Series
from src.modules.media.domain.value_objects import SeriesId
from src.shared_kernel.episode_composite_id import EpisodeCompositeId


class GetSeriesByIdUseCase:
    """Retrieve a series with all seasons and episodes.

    This use case fetches a complete series hierarchy from the repository,
    enriching each episode with watch progress data when available. Progress
    is resolved via ``ProgressLookupPort`` so the Media BC never imports
    Watch Progress domain types.

    Example:
        >>> use_case = GetSeriesByIdUseCase(uow_factory, progress_lookup)
        >>> result = await use_case.execute(GetSeriesByIdInput("ser_abc123"))
        >>> result.title
        'Breaking Bad'
        >>> len(result.seasons)
        5
    """

    def __init__(
        self,
        uow_factory: MediaUnitOfWorkFactory,
        progress_lookup: ProgressLookupPort,
    ) -> None:
        """Initialize the use case.

        Args:
            uow_factory: Factory that opens a fresh media Unit of Work.
            progress_lookup: Port for resolving watch progress snapshots.
        """
        self._uow_factory = uow_factory
        self._progress_lookup = progress_lookup

    async def execute(self, input_dto: GetSeriesByIdInput) -> SeriesOutput:
        """Execute the use case.

        Args:
            input_dto: Contains the series_id to fetch.

        Returns:
            SeriesOutput with complete hierarchy.

        Raises:
            ResourceNotFoundException: If series doesn't exist.
        """
        series_id = SeriesId(input_dto.series_id)
        async with self._uow_factory() as uow:
            series = await uow.series.find_by_id(series_id)

        if series is None:
            raise ResourceNotFoundException.for_resource("Series", input_dto.series_id)

        series_id_str = str(series.id)
        composite_ids = [
            EpisodeCompositeId.build(
                series_id_str, s.season_number.value, ep.episode_number.value
            ).media_id
            for s in series.seasons
            for ep in s.episodes
        ]
        progress_map = await self._progress_lookup.find_for_media_ids(composite_ids)

        return self._to_output(series, input_dto.lang, progress_map)

    def _to_output(
        self,
        series: Series,
        lang: str,
        progress_map: dict[str, ProgressSummary],
    ) -> SeriesOutput:
        """Convert Series entity to output DTO.

        Args:
            series: The Series entity to convert.
            lang: Language code for localized fields.
            progress_map: Map of composite media_id to progress summary.

        Returns:
            SeriesOutput with all fields and nested seasons/episodes.
        """
        series_id = str(series.id)
        return SeriesOutput(
            id=series_id,
            title=series.get_title(lang),
            original_title=series.original_title.value if series.original_title else None,
            start_year=series.start_year.value,
            end_year=series.end_year.value if series.end_year else None,
            is_ongoing=series.is_ongoing,
            synopsis=series.get_synopsis(lang),
            poster_path=series.poster_path.value if series.poster_path else None,
            backdrop_path=series.backdrop_path.value if series.backdrop_path else None,
            logo_path=series.logo_path.value if series.logo_path else None,
            genres=series.get_genres(lang),
            content_rating=series.content_rating.value if series.content_rating else None,
            trailer_url=series.trailer_url,
            tmdb_id=series.tmdb_id.value if series.tmdb_id else None,
            imdb_id=series.imdb_id.value if series.imdb_id else None,
            season_count=series.season_count,
            total_episodes=series.total_episodes,
            seasons=[self._to_season_output(s, series_id, progress_map) for s in series.seasons],
            created_at=series.created_at.isoformat(),
            updated_at=series.updated_at.isoformat(),
        )

    @staticmethod
    def _to_season_output(
        season: Season,
        series_id: str,
        progress_map: dict[str, ProgressSummary],
    ) -> SeasonOutput:
        """Convert Season entity to output DTO.

        Args:
            season: The Season entity to convert.
            series_id: External series ID for composite key lookup.
            progress_map: Map of composite media_id to progress summary.

        Returns:
            SeasonOutput with episode list.
        """
        return SeasonOutput(
            id=str(season.id) if season.id else None,
            season_number=season.season_number.value,
            title=season.title.value if season.title else None,
            synopsis=season.synopsis,
            poster_path=season.poster_path.value if season.poster_path else None,
            air_date=season.air_date.value.isoformat() if season.air_date else None,
            episode_count=season.episode_count,
            episodes=[
                GetSeriesByIdUseCase._to_episode_output(
                    e,
                    series_id,
                    season.season_number.value,
                    progress_map,
                )
                for e in season.episodes
            ],
        )

    @staticmethod
    def _to_episode_output(
        episode: Episode,
        series_id: str,
        season_number: int,
        progress_map: dict[str, ProgressSummary],
    ) -> EpisodeOutput:
        """Convert Episode entity to output DTO.

        Args:
            episode: The Episode entity to convert.
            series_id: External series ID for composite key lookup.
            season_number: Season number for composite key lookup.
            progress_map: Map of composite media_id to progress summary.

        Returns:
            EpisodeOutput with all fields including progress.
        """
        primary = episode.primary_file
        composite_key = EpisodeCompositeId.build(
            series_id,
            season_number,
            episode.episode_number.value,
        ).media_id
        progress = progress_map.get(composite_key)
        return EpisodeOutput(
            id=str(episode.id) if episode.id else None,
            episode_number=episode.episode_number.value,
            title=episode.title.value,
            synopsis=episode.synopsis,
            duration_seconds=episode.duration.value,
            duration_formatted=episode.duration.format_hms(),
            file_path=primary.file_path.value if primary else None,
            file_size=primary.file_size if primary else None,
            resolution=primary.resolution.value if primary else None,
            files=[to_media_file_output(f) for f in episode.files],
            thumbnail_path=episode.thumbnail_path.value if episode.thumbnail_path else None,
            scrub_preview_path=episode.scrub_preview_path.value
            if episode.scrub_preview_path
            else None,
            air_date=episode.air_date.value.isoformat() if episode.air_date else None,
            progress_percentage=progress.percentage if progress else None,
            position_seconds=progress.position_seconds if progress else None,
            watch_status=progress.status if progress else None,
            last_watched_at=progress.last_watched_at.isoformat() if progress else None,
        )


__all__ = ["GetSeriesByIdUseCase"]
