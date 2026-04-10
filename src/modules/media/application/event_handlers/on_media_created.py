"""Handler that auto-enriches media when created."""

import logging
from collections.abc import Awaitable, Callable

from src.building_blocks.application.event_bus import EventHandler
from src.building_blocks.domain.events import DomainEvent
from src.modules.media.application.dtos.enrichment_dtos import EnrichMediaInput
from src.modules.media.application.use_cases.enrich_movie_metadata import (
    EnrichMovieMetadataUseCase,
)
from src.modules.media.application.use_cases.enrich_series_metadata import (
    EnrichSeriesMetadataUseCase,
)
from src.modules.media.domain.events import MediaCreatedEvent

_logger = logging.getLogger(__name__)


class OnMediaCreatedHandler(EventHandler):
    """Auto-enrich movies and series when they are first created.

    Receives use case factories (callables) instead of instances to
    ensure each invocation gets a fresh use case with its own DB session.

    Example:
        >>> handler = OnMediaCreatedHandler(movie_uc_factory, series_uc_factory)
        >>> await handler.handle(MediaCreatedEvent(media_id="mov_abc", media_type="movie"))
    """

    def __init__(
        self,
        enrich_movie_factory: Callable[[], Awaitable[EnrichMovieMetadataUseCase]],
        enrich_series_factory: Callable[[], Awaitable[EnrichSeriesMetadataUseCase]],
    ) -> None:
        """Initialize the handler.

        Args:
            enrich_movie_factory: Factory that creates EnrichMovieMetadataUseCase.
            enrich_series_factory: Factory that creates EnrichSeriesMetadataUseCase.
        """
        self._enrich_movie_factory = enrich_movie_factory
        self._enrich_series_factory = enrich_series_factory

    async def handle(self, event: DomainEvent) -> None:
        """Handle a MediaCreatedEvent by enriching the media.

        Args:
            event: The domain event (expected to be MediaCreatedEvent).
        """
        if not isinstance(event, MediaCreatedEvent):
            return

        _logger.info("Auto-enriching %s %s", event.media_type, event.media_id)

        input_dto = EnrichMediaInput(media_id=event.media_id, force=False)

        if event.media_type == "movie":
            movie_uc = await self._enrich_movie_factory()
            result = await movie_uc.execute(input_dto)
        elif event.media_type == "series":
            series_uc = await self._enrich_series_factory()
            result = await series_uc.execute(input_dto)
        else:
            _logger.warning("Unknown media type: %s", event.media_type)
            return

        if result.enriched:
            _logger.info("Enriched %s %s via %s", event.media_type, event.media_id, result.provider)
        elif result.error:
            _logger.warning(
                "Failed to enrich %s %s: %s",
                event.media_type,
                event.media_id,
                result.error,
            )


__all__ = ["OnMediaCreatedHandler"]
