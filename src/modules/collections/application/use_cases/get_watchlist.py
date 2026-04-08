"""GetWatchlistUseCase - List watchlist items with media metadata."""

import logging

from src.modules.collections.application.dtos import (
    GetWatchlistInput,
    WatchlistItemOutput,
)
from src.modules.collections.domain.entities import WatchlistItem
from src.modules.collections.domain.repositories import WatchlistRepository
from src.modules.media.domain.repositories import MovieRepository, SeriesRepository
from src.modules.media.domain.value_objects import MovieId, SeriesId

_logger = logging.getLogger(__name__)


class GetWatchlistUseCase:
    """List all items in the user's watchlist with display metadata.

    Joins watchlist records with movie/series data to provide
    title and poster for the My List UI section.

    Example:
        >>> use_case = GetWatchlistUseCase(watchlist_repo, movie_repo, series_repo)
        >>> items = await use_case.execute(GetWatchlistInput(limit=50, lang="pt-BR"))
    """

    def __init__(
        self,
        watchlist_repository: WatchlistRepository,
        movie_repository: MovieRepository,
        series_repository: SeriesRepository,
    ) -> None:
        """Initialize the use case.

        Args:
            watchlist_repository: Repository for watchlist items.
            movie_repository: Repository for movie metadata.
            series_repository: Repository for series metadata.
        """
        self._watchlist_repo = watchlist_repository
        self._movie_repo = movie_repository
        self._series_repo = series_repository

    async def execute(self, input_dto: GetWatchlistInput) -> list[WatchlistItemOutput]:
        """Execute the use case.

        Args:
            input_dto: Contains limit and language.

        Returns:
            List of WatchlistItemOutput with media metadata.
        """
        items = await self._watchlist_repo.list_all(limit=input_dto.limit)
        _logger.info("Found %d watchlist items", len(items))

        result: list[WatchlistItemOutput] = []
        for item in items:
            output = await self._enrich_with_metadata(item, input_dto.lang)
            if output:
                result.append(output)
            else:
                _logger.warning("Could not find media for watchlist item: %s", item.media_id)

        return result

    async def _enrich_with_metadata(
        self,
        item: WatchlistItem,
        lang: str,
    ) -> WatchlistItemOutput | None:
        """Enrich a watchlist item with media metadata.

        Args:
            item: The watchlist item.
            lang: Language code for localized metadata.

        Returns:
            WatchlistItemOutput with metadata, or None if media not found.
        """
        if item.media_type == "movie":
            movie = await self._movie_repo.find_by_id(MovieId(item.media_id))
            if not movie:
                return None
            return WatchlistItemOutput.from_entity(
                entity=item,
                title=movie.get_title(lang),
                poster_path=movie.poster_path.value if movie.poster_path else None,
            )

        if item.media_type == "series":
            series = await self._series_repo.find_by_id(SeriesId(item.media_id))
            if not series:
                return None
            return WatchlistItemOutput.from_entity(
                entity=item,
                title=series.get_title(lang),
                poster_path=series.poster_path.value if series.poster_path else None,
            )

        return None


__all__ = ["GetWatchlistUseCase"]
