"""GetFileVariantsUseCase - List all file variants of a movie or episode."""

from src.building_blocks.application.errors import ResourceNotFoundException
from src.modules.media.application.dtos.media_file_dtos import (
    GetFileVariantsInput,
    MediaFileOutput,
)
from src.modules.media.application.unit_of_work import MediaUnitOfWorkFactory
from src.modules.media.application.use_cases._media_file_helpers import (
    to_media_file_output,
)
from src.modules.media.domain.value_objects import EpisodeId, MovieId


class GetFileVariantsUseCase:
    """List all file variants of a movie or episode.

    Example:
        >>> use_case = GetFileVariantsUseCase(uow_factory)
        >>> variants = await use_case.execute(
        ...     GetFileVariantsInput(media_id="mov_abc123"),
        ... )
        >>> len(variants)
        3
    """

    def __init__(self, uow_factory: MediaUnitOfWorkFactory) -> None:
        """Initialize the use case.

        Args:
            uow_factory: Factory that opens a fresh media Unit of Work.
        """
        self._uow_factory = uow_factory

    async def execute(self, input_dto: GetFileVariantsInput) -> list[MediaFileOutput]:
        """Execute the use case.

        Args:
            input_dto: Contains the media_id.

        Returns:
            List of MediaFileOutput for all file variants.

        Raises:
            ResourceNotFoundException: If the entity doesn't exist.
        """
        prefix = input_dto.media_id.split("_")[0] if "_" in input_dto.media_id else ""

        async with self._uow_factory() as uow:
            if prefix == "mov":
                movie = await uow.movies.find_by_id(MovieId(input_dto.media_id))
                if movie is None:
                    raise ResourceNotFoundException.for_resource("Movie", input_dto.media_id)
                return [to_media_file_output(f) for f in movie.files]

            if prefix == "epi":
                series = await uow.series.find_by_episode_id(
                    EpisodeId(input_dto.media_id),
                )
                if series is None:
                    raise ResourceNotFoundException.for_resource("Episode", input_dto.media_id)

                for season in series.seasons:
                    for episode in season.episodes:
                        if str(episode.id) == input_dto.media_id:
                            return [to_media_file_output(f) for f in episode.files]

        raise ResourceNotFoundException.for_resource("Media", input_dto.media_id)


__all__ = ["GetFileVariantsUseCase"]
