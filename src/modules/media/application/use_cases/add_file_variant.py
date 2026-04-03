"""AddFileVariantUseCase - Add a file variant to a movie or episode."""

from src.building_blocks.application.errors import ResourceNotFoundException
from src.modules.media.application.dtos.media_file_dtos import (
    AddFileVariantInput,
    MediaFileOutput,
)
from src.modules.media.application.use_cases._media_file_helpers import (
    to_media_file_output,
)
from src.modules.media.domain.repositories import MovieRepository, SeriesRepository
from src.modules.media.domain.value_objects import (
    EpisodeId,
    HdrFormat,
    MediaFile,
    MovieId,
    Resolution,
    VideoCodec,
)
from src.shared_kernel.value_objects.file_path import FilePath


class AddFileVariantUseCase:
    """Add a file variant to a movie or episode.

    Determines the target entity from the media_id prefix and adds
    the new file variant to its file list.

    Example:
        >>> use_case = AddFileVariantUseCase(movie_repo, series_repo)
        >>> result = await use_case.execute(AddFileVariantInput(
        ...     media_id="mov_abc123",
        ...     file_path="/movies/inception_4k.mkv",
        ...     file_size=48_000_000_000,
        ...     resolution="4K",
        ... ))
    """

    def __init__(
        self,
        movie_repository: MovieRepository,
        series_repository: SeriesRepository,
    ) -> None:
        """Initialize the use case.

        Args:
            movie_repository: Repository for movie persistence.
            series_repository: Repository for series persistence.
        """
        self._movie_repository = movie_repository
        self._series_repository = series_repository

    async def execute(self, input_dto: AddFileVariantInput) -> MediaFileOutput:
        """Execute the use case.

        Args:
            input_dto: Contains the media_id and file metadata.

        Returns:
            MediaFileOutput of the added file variant.

        Raises:
            ResourceNotFoundException: If the target entity doesn't exist.
        """
        media_file = MediaFile(
            file_path=FilePath(input_dto.file_path),
            file_size=input_dto.file_size,
            resolution=Resolution(input_dto.resolution),
            video_codec=VideoCodec(input_dto.video_codec) if input_dto.video_codec else None,
            video_bitrate=input_dto.video_bitrate,
            hdr_format=HdrFormat(input_dto.hdr_format) if input_dto.hdr_format else None,
            is_primary=input_dto.is_primary,
        )

        prefix = input_dto.media_id.split("_")[0] if "_" in input_dto.media_id else ""

        if prefix == "mov":
            return await self._add_to_movie(input_dto.media_id, media_file)
        if prefix == "epi":
            return await self._add_to_episode(input_dto.media_id, media_file)

        raise ResourceNotFoundException.for_resource("Media", input_dto.media_id)

    async def _add_to_movie(self, movie_id: str, media_file: MediaFile) -> MediaFileOutput:
        movie = await self._movie_repository.find_by_id(MovieId(movie_id))
        if movie is None:
            raise ResourceNotFoundException.for_resource("Movie", movie_id)

        movie = movie.with_file(media_file)
        await self._movie_repository.save(movie)
        return to_media_file_output(media_file)

    async def _add_to_episode(self, episode_id: str, media_file: MediaFile) -> MediaFileOutput:
        series = await self._series_repository.find_by_episode_id(EpisodeId(episode_id))
        if series is None:
            raise ResourceNotFoundException.for_resource("Episode", episode_id)

        # Navigate hierarchy to find and update the episode
        updated_seasons = []
        for season in series.seasons:
            updated_episodes = []
            for ep in season.episodes:
                updated_ep = ep.with_file(media_file) if str(ep.id) == episode_id else ep
                updated_episodes.append(updated_ep)
            updated_seasons.append(season.with_updates(episodes=updated_episodes))

        updated_series = series.with_updates(seasons=updated_seasons)
        await self._series_repository.save(updated_series)
        return to_media_file_output(media_file)


__all__ = ["AddFileVariantUseCase"]
