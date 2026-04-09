"""GetWatchlistUseCase - List watchlist items with media metadata."""

import logging

from src.modules.collections.application.dtos import (
    GetWatchlistInput,
    WatchlistItemOutput,
)
from src.modules.collections.domain.repositories import WatchlistRepository
from src.modules.media.domain.repositories import MovieRepository, SeriesRepository
from src.modules.media.domain.value_objects import MovieId, SeriesId
from src.shared_kernel.value_objects import CollectionMediaType

_logger = logging.getLogger(__name__)


class GetWatchlistUseCase:
    """List all items in the user's watchlist with display metadata.

    Joins watchlist records with movie/series data to provide
    title and poster for the My List UI section. Uses batch
    lookups to avoid N+1 queries.

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

        result: list[WatchlistItemOutput] = []
        for item in items:
            if item.media_type == CollectionMediaType.MOVIE:
                movie = movies_map.get(item.media_id)
                if not movie:
                    _logger.warning("Could not find media for watchlist item: %s", item.media_id)
                    continue
                result.append(
                    WatchlistItemOutput.from_entity(
                        entity=item,
                        title=movie.get_title(input_dto.lang),
                        poster_path=movie.poster_path.value if movie.poster_path else None,
                    )
                )
            elif item.media_type == CollectionMediaType.SERIES:
                series = series_map.get(item.media_id)
                if not series:
                    _logger.warning("Could not find media for watchlist item: %s", item.media_id)
                    continue
                result.append(
                    WatchlistItemOutput.from_entity(
                        entity=item,
                        title=series.get_title(input_dto.lang),
                        poster_path=series.poster_path.value if series.poster_path else None,
                    )
                )

        return result


__all__ = ["GetWatchlistUseCase"]
