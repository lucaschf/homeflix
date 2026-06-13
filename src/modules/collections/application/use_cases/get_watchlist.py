"""GetWatchlistUseCase - List watchlist items with media metadata."""

import logging

from src.modules.collections.application.dtos import (
    GetWatchlistInput,
    WatchlistItemOutput,
)
from src.modules.collections.application.ports import MediaLookupPort
from src.modules.collections.application.unit_of_work import CollectionsUnitOfWorkFactory
from src.shared_kernel.value_objects import CollectionMediaType
from src.shared_kernel.value_objects.profile_id import ProfileId

_logger = logging.getLogger(__name__)


class GetWatchlistUseCase:
    """List all items in the user's watchlist with display metadata.

    Joins watchlist records with the Media BC's display data (title,
    poster) via ``MediaLookupPort`` so this use case never talks to
    media repositories directly. Uses a single batch lookup to avoid
    N+1 queries.

    Example:
        >>> use_case = GetWatchlistUseCase(uow_factory, media_lookup)
        >>> items = await use_case.execute(GetWatchlistInput(limit=50, lang="pt-BR"))
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

    async def execute(self, input_dto: GetWatchlistInput) -> list[WatchlistItemOutput]:
        """Execute the use case.

        Args:
            input_dto: Contains limit and language.

        Returns:
            List of WatchlistItemOutput with media metadata.
        """
        profile_id = ProfileId(input_dto.profile_id)
        async with self._uow_factory() as uow:
            items = await uow.watchlist.list_all(profile_id, limit=input_dto.limit)
        _logger.info("Found %d watchlist items", len(items))

        if not items:
            return []

        movie_ids = [
            i.media_id.as_movie_id() for i in items if i.media_type == CollectionMediaType.MOVIE
        ]
        series_ids = [
            i.media_id.as_series_id() for i in items if i.media_type == CollectionMediaType.SERIES
        ]

        summaries = await self._media_lookup.get_many(movie_ids, series_ids, input_dto.lang)

        result: list[WatchlistItemOutput] = []
        for item in items:
            summary = summaries.get((item.media_type, item.media_id.value))
            if summary is None:
                _logger.warning("Could not find media for watchlist item: %s", item.media_id)
                continue
            result.append(
                WatchlistItemOutput.from_entity(
                    entity=item,
                    title=summary.title,
                    poster_path=summary.poster_path,
                )
            )

        return result


__all__ = ["GetWatchlistUseCase"]
