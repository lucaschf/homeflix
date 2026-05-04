"""GetCustomListItemsUseCase - List items in a custom list with metadata."""

import logging

from src.building_blocks.application.errors import ResourceNotFoundException
from src.modules.collections.application.dtos import (
    CustomListItemOutput,
    GetCustomListItemsInput,
)
from src.modules.collections.application.ports import MediaLookupPort
from src.modules.collections.application.unit_of_work import CollectionsUnitOfWorkFactory
from src.shared_kernel.value_objects import CollectionMediaType
from src.shared_kernel.value_objects.profile_id import ProfileId

_logger = logging.getLogger(__name__)


class GetCustomListItemsUseCase:
    """List all items in a custom list with display metadata.

    Joins list items with the Media BC's display data (title, poster)
    via ``MediaLookupPort``. Uses a single batch lookup to avoid N+1.

    Example:
        >>> use_case = GetCustomListItemsUseCase(uow_factory, media_lookup)
        >>> items = await use_case.execute(
        ...     GetCustomListItemsInput(list_id="lst_abc123", lang="pt-BR"),
        ... )
    """

    def __init__(
        self,
        uow_factory: CollectionsUnitOfWorkFactory,
        media_lookup: MediaLookupPort,
    ) -> None:
        """Initialize the use case.

        Args:
            uow_factory: Factory that opens a fresh collections Unit of Work.
            media_lookup: Port for resolving media display metadata.
        """
        self._uow_factory = uow_factory
        self._media_lookup = media_lookup

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
        profile_id = ProfileId(input_dto.profile_id)
        async with self._uow_factory() as uow:
            custom_list = await uow.custom_lists.find_by_id(input_dto.list_id, profile_id)
            if not custom_list:
                raise ResourceNotFoundException.for_resource("CustomList", input_dto.list_id)

            items = await uow.custom_lists.list_items(input_dto.list_id, profile_id)
        _logger.info("Found %d items in custom list %s", len(items), input_dto.list_id)

        if not items:
            return []

        movie_ids = [i.media_id for i in items if i.media_type == CollectionMediaType.MOVIE]
        series_ids = [i.media_id for i in items if i.media_type == CollectionMediaType.SERIES]

        summaries = await self._media_lookup.get_many(movie_ids, series_ids, input_dto.lang)

        result: list[CustomListItemOutput] = []
        for item in items:
            summary = summaries.get((item.media_type, item.media_id))
            if summary is None:
                _logger.warning(
                    "Could not find media for custom list item: %s",
                    item.media_id,
                )
                continue
            result.append(
                CustomListItemOutput.from_entity(
                    entity=item,
                    title=summary.title,
                    poster_path=summary.poster_path,
                )
            )

        return result


__all__ = ["GetCustomListItemsUseCase"]
