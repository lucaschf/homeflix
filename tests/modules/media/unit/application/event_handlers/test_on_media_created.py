"""Tests for OnMediaCreatedHandler's provider budget (ADR-038)."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.building_blocks.application.deadline import remaining_seconds
from src.modules.media.application.dtos.enrichment_dtos import (
    EnrichMediaInput,
    EnrichMediaOutput,
)
from src.modules.media.application.event_handlers.on_media_created import (
    OnMediaCreatedHandler,
)
from src.modules.media.domain.events import MediaCreatedEvent
from src.modules.media.domain.value_objects import MovieId
from src.shared_kernel.value_objects.media_type import MediaType


@pytest.mark.unit
async def test_auto_enrichment_runs_under_a_declared_budget() -> None:
    """A background auto-enrich may wait out a short Retry-After; it is not interactive."""
    budgets: list[float | None] = []

    async def enrich(input_dto: EnrichMediaInput) -> EnrichMediaOutput:
        budgets.append(remaining_seconds())
        return EnrichMediaOutput(media_id=input_dto.media_id, enriched=True, provider="tmdb")

    movie_uc = MagicMock()
    movie_uc.execute = AsyncMock(side_effect=enrich)
    handler = OnMediaCreatedHandler(
        enrich_movie_factory=AsyncMock(return_value=movie_uc),
        enrich_series_factory=AsyncMock(),
    )

    await handler.handle(MediaCreatedEvent(media_id=MovieId.generate(), media_type=MediaType.MOVIE))

    assert len(budgets) == 1
    assert budgets[0] is not None
    assert 0 < budgets[0] <= OnMediaCreatedHandler.ENRICH_BUDGET_SECONDS
