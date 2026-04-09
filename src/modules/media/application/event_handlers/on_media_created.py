"""Handler that auto-enriches media when created."""

import logging

from src.building_blocks.application.event_bus import EventHandler
from src.building_blocks.domain.events import DomainEvent, MediaCreatedEvent
from src.modules.media.application.dtos.enrichment_dtos import EnrichMediaInput
from src.modules.media.application.use_cases.enrich_movie_metadata import (
    EnrichMovieMetadataUseCase,
)
from src.modules.media.application.use_cases.enrich_series_metadata import (
    EnrichSeriesMetadataUseCase,
)

_logger = logging.getLogger(__name__)


class OnMediaCreatedHandler(EventHandler):
    """Auto-enrich movies and series when they are first created.

    Listens to MediaCreatedEvent and dispatches to the appropriate
    enrich use case. Failures are logged but never raised.

    Example:
        >>> handler = OnMediaCreatedHandler(enrich_movie, enrich_series)
        >>> await handler.handle(MediaCreatedEvent(media_id="mov_abc", media_type="movie"))
    """

    def __init__(
        self,
        enrich_movie: EnrichMovieMetadataUseCase,
        enrich_series: EnrichSeriesMetadataUseCase,
    ) -> None:
        """Initialize the handler.

        Args:
            enrich_movie: Use case for enriching movie metadata.
            enrich_series: Use case for enriching series metadata.
        """
        self._enrich_movie = enrich_movie
        self._enrich_series = enrich_series

    async def handle(self, event: DomainEvent) -> None:
        """Handle a MediaCreatedEvent by enriching the media.

        Args:
            event: The domain event (expected to be MediaCreatedEvent).
        """
        if not isinstance(event, MediaCreatedEvent):
            return

        _logger.info(
            "Auto-enriching %s %s",
            event.media_type,
            event.media_id,
        )

        input_dto = EnrichMediaInput(media_id=event.media_id, force=False)

        if event.media_type == "movie":
            result = await self._enrich_movie.execute(input_dto)
        elif event.media_type == "series":
            result = await self._enrich_series.execute(input_dto)
        else:
            _logger.warning("Unknown media type: %s", event.media_type)
            return

        if result.enriched:
            _logger.info("Enriched %s %s via %s", event.media_type, event.media_id, result.provider)
        elif result.error:
            _logger.warning(
                "Failed to enrich %s %s: %s", event.media_type, event.media_id, result.error
            )


__all__ = ["OnMediaCreatedHandler"]
