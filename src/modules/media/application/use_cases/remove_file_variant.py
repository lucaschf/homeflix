"""RemoveFileVariantUseCase - Remove a file variant from a movie or episode."""

from src.building_blocks.application.errors import (
    ResourceNotFoundException,
    UseCaseValidationException,
)
from src.modules.media.application.dtos.media_file_dtos import RemoveFileVariantInput
from src.modules.media.application.unit_of_work import (
    MediaUnitOfWork,
    MediaUnitOfWorkFactory,
)
from src.modules.media.domain.entities.file_variant_mixin import FileVariantMixin
from src.modules.media.domain.value_objects import EpisodeId, MediaFile, MovieId
from src.shared_kernel.value_objects.file_path import FilePath


class RemoveFileVariantUseCase:
    """Remove a file variant from a movie or episode.

    If the removed file was the primary, the best remaining file
    is promoted to primary.

    Example:
        >>> use_case = RemoveFileVariantUseCase(uow_factory)
        >>> await use_case.execute(RemoveFileVariantInput(
        ...     media_id="mov_abc123",
        ...     file_path="/movies/inception_720p.mkv",
        ... ))
    """

    def __init__(self, uow_factory: MediaUnitOfWorkFactory) -> None:
        """Initialize the use case.

        Args:
            uow_factory: Factory that opens a fresh media Unit of Work.
        """
        self._uow_factory = uow_factory

    async def execute(self, input_dto: RemoveFileVariantInput) -> None:
        """Execute the use case.

        Args:
            input_dto: Contains the media_id and file_path to remove.

        Raises:
            ResourceNotFoundException: If the entity or file variant doesn't exist.
            UseCaseValidationException: If trying to remove the last file variant.
        """
        prefix = input_dto.media_id.split("_")[0] if "_" in input_dto.media_id else ""

        async with self._uow_factory() as uow:
            if prefix == "mov":
                await self._remove_from_movie(uow, input_dto)
                return
            if prefix == "epi":
                await self._remove_from_episode(uow, input_dto)
                return

        raise ResourceNotFoundException.for_resource("Media", input_dto.media_id)

    @staticmethod
    async def _remove_from_movie(
        uow: MediaUnitOfWork,
        input_dto: RemoveFileVariantInput,
    ) -> None:
        movie = await uow.movies.find_by_id(MovieId(input_dto.media_id))
        if movie is None:
            raise ResourceNotFoundException.for_resource("Movie", input_dto.media_id)

        new_files = _remove_file_and_promote(movie, input_dto.file_path)
        movie = movie.with_updates(files=new_files)
        await uow.movies.save(movie)

    @staticmethod
    async def _remove_from_episode(
        uow: MediaUnitOfWork,
        input_dto: RemoveFileVariantInput,
    ) -> None:
        series = await uow.series.find_by_episode_id(EpisodeId(input_dto.media_id))
        if series is None:
            raise ResourceNotFoundException.for_resource("Episode", input_dto.media_id)

        updated_seasons = []
        for season in series.seasons:
            updated_episodes = []
            for ep in season.episodes:
                if str(ep.id) == input_dto.media_id:
                    new_files = _remove_file_and_promote(ep, input_dto.file_path)
                    updated_episodes.append(ep.with_updates(files=new_files))
                else:
                    updated_episodes.append(ep)
            updated_seasons.append(season.with_updates(episodes=updated_episodes))

        updated_series = series.with_updates(seasons=updated_seasons)
        await uow.series.save(updated_series)


def _remove_file_and_promote(
    entity: FileVariantMixin,
    file_path: str,
) -> list[MediaFile]:
    """Remove a file variant and promote best remaining if needed.

    Args:
        entity: The entity with file variants.
        file_path: Path of the file to remove.

    Returns:
        Updated file list.

    Raises:
        ResourceNotFoundException: If file_path not found.
        UseCaseValidationException: If removing the last file.
    """
    target_path = FilePath(file_path)
    matching = [f for f in entity.files if f.file_path == target_path]

    if not matching:
        raise ResourceNotFoundException.for_resource("FileVariant", file_path)

    if len(entity.files) == 1:
        raise UseCaseValidationException(
            message="Cannot remove the last file variant",
            message_code="CANNOT_REMOVE_LAST_FILE_VARIANT",
        )

    removed = matching[0]
    remaining = [f for f in entity.files if f.file_path != target_path]

    # Promote best remaining if the removed file was primary
    if removed.is_primary and remaining:
        best = max(remaining, key=lambda f: f.resolution.total_pixels)
        remaining = [
            MediaFile(
                file_path=f.file_path,
                file_size=f.file_size,
                resolution=f.resolution,
                video_codec=f.video_codec,
                video_bitrate=f.video_bitrate,
                hdr_format=f.hdr_format,
                audio_tracks=f.audio_tracks,
                subtitle_tracks=f.subtitle_tracks,
                is_primary=(f is best),
                added_at=f.added_at,
            )
            for f in remaining
        ]

    return remaining


__all__ = ["RemoveFileVariantUseCase"]
