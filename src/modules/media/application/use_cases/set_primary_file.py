"""SetPrimaryFileUseCase - Set a file variant as primary."""

from src.building_blocks.application.errors import ResourceNotFoundException
from src.modules.media.application.dtos.media_file_dtos import (
    MediaFileOutput,
    SetPrimaryFileInput,
)
from src.modules.media.application.unit_of_work import (
    MediaUnitOfWork,
    MediaUnitOfWorkFactory,
)
from src.modules.media.application.use_cases._media_file_helpers import (
    to_media_file_output,
)
from src.modules.media.domain.entities.file_variant_mixin import FileVariantMixin
from src.modules.media.domain.value_objects import EpisodeId, MediaFile, MovieId
from src.shared_kernel.value_objects.file_path import FilePath


class SetPrimaryFileUseCase:
    """Set a specific file variant as the primary for a movie or episode.

    Clears is_primary from all other variants and sets it on the
    specified file_path.

    Example:
        >>> use_case = SetPrimaryFileUseCase(uow_factory)
        >>> result = await use_case.execute(SetPrimaryFileInput(
        ...     media_id="mov_abc123",
        ...     file_path="/movies/inception_4k.mkv",
        ... ))
    """

    def __init__(self, uow_factory: MediaUnitOfWorkFactory) -> None:
        """Initialize the use case.

        Args:
            uow_factory: Factory that opens a fresh media Unit of Work.
        """
        self._uow_factory = uow_factory

    async def execute(self, input_dto: SetPrimaryFileInput) -> list[MediaFileOutput]:
        """Execute the use case.

        Args:
            input_dto: Contains the media_id and file_path to set as primary.

        Returns:
            Updated list of MediaFileOutput for all variants.

        Raises:
            ResourceNotFoundException: If entity or file variant doesn't exist.
        """
        prefix = input_dto.media_id.split("_")[0] if "_" in input_dto.media_id else ""

        async with self._uow_factory() as uow:
            if prefix == "mov":
                return await self._set_for_movie(uow, input_dto)
            if prefix == "epi":
                return await self._set_for_episode(uow, input_dto)

        raise ResourceNotFoundException.for_resource("Media", input_dto.media_id)

    @staticmethod
    async def _set_for_movie(
        uow: MediaUnitOfWork,
        input_dto: SetPrimaryFileInput,
    ) -> list[MediaFileOutput]:
        movie = await uow.movies.find_by_id(MovieId(input_dto.media_id))
        if movie is None:
            raise ResourceNotFoundException.for_resource("Movie", input_dto.media_id)

        new_files = _switch_primary(movie, input_dto.file_path)
        movie = movie.with_updates(files=new_files)
        saved = await uow.movies.save(movie)
        return [to_media_file_output(f) for f in saved.files]

    @staticmethod
    async def _set_for_episode(
        uow: MediaUnitOfWork,
        input_dto: SetPrimaryFileInput,
    ) -> list[MediaFileOutput]:
        series = await uow.series.find_by_episode_id(EpisodeId(input_dto.media_id))
        if series is None:
            raise ResourceNotFoundException.for_resource("Episode", input_dto.media_id)

        result_files: list[MediaFileOutput] = []
        updated_seasons = []
        for season in series.seasons:
            updated_episodes = []
            for ep in season.episodes:
                if str(ep.id) == input_dto.media_id:
                    new_files = _switch_primary(ep, input_dto.file_path)
                    updated_ep = ep.with_updates(files=new_files)
                    result_files = [to_media_file_output(f) for f in updated_ep.files]
                    updated_episodes.append(updated_ep)
                else:
                    updated_episodes.append(ep)
            updated_seasons.append(season.with_updates(episodes=updated_episodes))

        updated_series = series.with_updates(seasons=updated_seasons)
        await uow.series.save(updated_series)
        return result_files


def _switch_primary(entity: FileVariantMixin, file_path: str) -> list[MediaFile]:
    """Switch the primary flag to the specified file_path.

    Args:
        entity: The entity with file variants.
        file_path: Path of the file to set as primary.

    Returns:
        Updated file list with new primary.

    Raises:
        ResourceNotFoundException: If file_path not found among variants.
    """
    target_path = FilePath(file_path)
    if not any(f.file_path == target_path for f in entity.files):
        raise ResourceNotFoundException.for_resource("FileVariant", file_path)

    return [
        MediaFile(
            file_path=f.file_path,
            file_size=f.file_size,
            resolution=f.resolution,
            video_codec=f.video_codec,
            video_bitrate=f.video_bitrate,
            hdr_format=f.hdr_format,
            audio_tracks=f.audio_tracks,
            subtitle_tracks=f.subtitle_tracks,
            is_primary=(f.file_path == target_path),
            added_at=f.added_at,
        )
        for f in entity.files
    ]


__all__ = ["SetPrimaryFileUseCase"]
