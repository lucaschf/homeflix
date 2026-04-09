"""GetCustomListItemsUseCase - List items in a custom list with metadata."""

import logging

from src.building_blocks.application.errors import ResourceNotFoundException
from src.modules.collections.application.dtos import (
    CustomListItemOutput,
    GetCustomListItemsInput,
)
from src.modules.collections.domain.repositories import CustomListRepository
from src.modules.media.domain.repositories import MovieRepository, SeriesRepository
from src.modules.media.domain.value_objects import MovieId, SeriesId
from src.shared_kernel.value_objects import CollectionMediaType

_logger = logging.getLogger(__name__)


class GetCustomListItemsUseCase:
    """List all items in a custom list with display metadata.

    Joins list items with movie/series data to provide
    title and poster for the UI. Uses batch lookups to avoid N+1.

    Example:
        >>> use_case = GetCustomListItemsUseCase(
        ...     custom_list_repo, movie_repo, series_repo,
        ... )
        >>> items = await use_case.execute(
        ...     GetCustomListItemsInput(list_id="lst_abc123", lang="pt-BR"),
        ... )
    """

    def __init__(
        self,
        custom_list_repository: CustomListRepository,
        movie_repository: MovieRepository,
        series_repository: SeriesRepository,
    ) -> None:
        """Initialize the use case.

        Args:
            custom_list_repository: Repository for custom list items.
            movie_repository: Repository for movie metadata.
            series_repository: Repository for series metadata.
        """
        self._list_repo = custom_list_repository
        self._movie_repo = movie_repository
        self._series_repo = series_repository

    async def execute(
        self,
        input_dto: GetCustomListItemsInput,
    ) -> list[CustomListItemOutput]:
        """Execute the use case.

        Args:
            input_dto: Contains list_id and language.

        Returns:
            List of CustomListItemOutput with media metadata.

        Raises:
            ResourceNotFoundException: If the list does not exist.
        """
        custom_list = await self._list_repo.find_by_id(input_dto.list_id)
        if not custom_list:
            raise ResourceNotFoundException.for_resource("CustomList", input_dto.list_id)

        items = await self._list_repo.list_items(input_dto.list_id)
        _logger.info("Found %d items in custom list %s", len(items), input_dto.list_id)

        if not items:
            return []

        # Batch-load all referenced movies and series
        movie_ids = [
            MovieId(i.media_id) for i in items if i.media_type == CollectionMediaType.MOVIE
        ]
        series_ids = [
            SeriesId(i.media_id) for i in items if i.media_type == CollectionMediaType.SERIES
        ]

        movies_map = await self._movie_repo.find_by_ids(movie_ids) if movie_ids else {}
        series_map = await self._series_repo.find_by_ids(series_ids) if series_ids else {}

        result: list[CustomListItemOutput] = []
        for item in items:
            if item.media_type == CollectionMediaType.MOVIE:
                movie = movies_map.get(item.media_id)
                if not movie:
                    _logger.warning("Could not find movie for custom list item: %s", item.media_id)
                    continue
                result.append(
                    CustomListItemOutput.from_entity(
                        entity=item,
                        title=movie.get_title(input_dto.lang),
                        poster_path=movie.poster_path.value if movie.poster_path else None,
                    )
                )
            elif item.media_type == CollectionMediaType.SERIES:
                series = series_map.get(item.media_id)
                if not series:
                    _logger.warning("Could not find series for custom list item: %s", item.media_id)
                    continue
                result.append(
                    CustomListItemOutput.from_entity(
                        entity=item,
                        title=series.get_title(input_dto.lang),
                        poster_path=series.poster_path.value if series.poster_path else None,
                    )
                )

        return result


__all__ = ["GetCustomListItemsUseCase"]
