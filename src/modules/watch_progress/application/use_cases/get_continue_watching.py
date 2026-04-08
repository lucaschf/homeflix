"""GetContinueWatchingUseCase - List in-progress items with media details."""

import logging

from src.modules.media.domain.repositories import MovieRepository
from src.modules.watch_progress.application.dtos import (
    ContinueWatchingItem,
    ContinueWatchingOutput,
    GetContinueWatchingInput,
)
from src.modules.watch_progress.domain.entities import WatchProgress
from src.modules.watch_progress.domain.repositories import WatchProgressRepository

_logger = logging.getLogger(__name__)


class GetContinueWatchingUseCase:
    """List in-progress media items with display metadata.

    Joins progress records with movie data to provide title and
    poster for the "Continue Watching" UI section.

    Example:
        >>> use_case = GetContinueWatchingUseCase(progress_repo, movie_repo)
        >>> result = await use_case.execute(GetContinueWatchingInput(limit=10))
    """

    def __init__(
        self,
        progress_repository: WatchProgressRepository,
        movie_repository: MovieRepository,
    ) -> None:
        """Initialize the use case.

        Args:
            progress_repository: Repository for watch progress.
            movie_repository: Repository for movie metadata.
        """
        self._progress_repo = progress_repository
        self._movie_repo = movie_repository

    async def execute(self, input_dto: GetContinueWatchingInput) -> ContinueWatchingOutput:
        """Execute the use case.

        Args:
            input_dto: Contains limit and language.

        Returns:
            ContinueWatchingOutput with items including media metadata.
        """
        progress_list = await self._progress_repo.list_in_progress(limit=input_dto.limit)
        _logger.info("Found %d in-progress items", len(progress_list))

        items: list[ContinueWatchingItem] = []
        for progress in progress_list:
            _logger.info(
                "Enriching progress: media_id=%s, media_type=%s",
                progress.media_id,
                progress.media_type,
            )
            item = await self._enrich_with_metadata(progress, input_dto.lang)
            if item:
                items.append(item)
            else:
                _logger.warning("Could not find media for progress: %s", progress.media_id)

        return ContinueWatchingOutput(items=items)

    async def _enrich_with_metadata(
        self,
        progress: WatchProgress,
        lang: str,
    ) -> ContinueWatchingItem | None:
        """Enrich a progress record with media metadata.

        Args:
            progress: The watch progress record.
            lang: Language code for localized metadata.

        Returns:
            ContinueWatchingItem with metadata, or None if media not found.
        """
        if progress.media_type == "movie":
            from src.modules.media.domain.value_objects import MovieId

            movie = await self._movie_repo.find_by_id(MovieId(progress.media_id))
            if not movie:
                return None
            return ContinueWatchingItem(
                media_id=progress.media_id,
                media_type=progress.media_type,
                title=movie.get_title(lang),
                poster_path=movie.poster_path.value if movie.poster_path else None,
                backdrop_path=movie.backdrop_path.value if movie.backdrop_path else None,
                position_seconds=progress.position_seconds,
                duration_seconds=progress.duration_seconds,
                percentage=progress.percentage,
                last_watched_at=progress.last_watched_at.isoformat(),
            )

        # TODO: episode support (requires series repo lookup)
        return None


__all__ = ["GetContinueWatchingUseCase"]
