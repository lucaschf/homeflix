"""GetCustomListItemsUseCase - List items in a custom list with metadata."""

import logging

from src.building_blocks.application.errors import ResourceNotFoundException
from src.modules.collections.application.dtos import (
    CustomListItemOutput,
    GetCustomListItemsInput,
)
from src.modules.collections.domain.entities import CustomListItem
from src.modules.collections.domain.repositories import CustomListRepository
from src.modules.media.domain.repositories import MovieRepository, SeriesRepository
from src.modules.media.domain.value_objects import MovieId, SeriesId

_logger = logging.getLogger(__name__)


class GetCustomListItemsUseCase:
    """List all items in a custom list with display metadata.

    Joins list items with movie/series data to provide
    title and poster for the UI.

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

        result: list[CustomListItemOutput] = []
        for item in items:
            output = await self._enrich_with_metadata(item, input_dto.lang)
            if output:
                result.append(output)
            else:
                _logger.warning(
                    "Could not find media for custom list item: %s",
                    item.media_id,
                )

        return result

    async def _enrich_with_metadata(
        self,
        item: CustomListItem,
        lang: str,
    ) -> CustomListItemOutput | None:
        """Enrich a custom list item with media metadata.

        Args:
            item: The custom list item.
            lang: Language code for localized metadata.

        Returns:
            CustomListItemOutput with metadata, or None if media not found.
        """
        if item.media_type == "movie":
            movie = await self._movie_repo.find_by_id(MovieId(item.media_id))
            if not movie:
                return None
            return CustomListItemOutput.from_entity(
                entity=item,
                title=movie.get_title(lang),
                poster_path=movie.poster_path.value if movie.poster_path else None,
            )

        if item.media_type == "series":
            series = await self._series_repo.find_by_id(SeriesId(item.media_id))
            if not series:
                return None
            return CustomListItemOutput.from_entity(
                entity=item,
                title=series.get_title(lang),
                poster_path=series.poster_path.value if series.poster_path else None,
            )

        return None


__all__ = ["GetCustomListItemsUseCase"]
