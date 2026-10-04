"""Use case for bulk metadata enrichment of all media."""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import ClassVar

from src.building_blocks.application.deadline import deadline
from src.building_blocks.infrastructure.errors import (
    GatewayException,
    GatewayRateLimitException,
)
from src.modules.media.application.dtos.enrichment_dtos import (
    BulkEnrichInput,
    BulkEnrichOutput,
    EnrichMediaInput,
    EnrichMediaOutput,
)
from src.modules.media.application.unit_of_work import MediaUnitOfWorkFactory
from src.modules.media.application.use_cases.enrich_movie_metadata import (
    EnrichMovieMetadataUseCase,
)
from src.modules.media.application.use_cases.enrich_series_metadata import (
    EnrichSeriesMetadataUseCase,
)


@dataclass
class _BatchState:
    """Progress of one bulk run, shared by the movie and series passes."""

    started_at: float
    errors: list[str] = field(default_factory=list)
    consecutive_provider_failures: int = 0
    aborted_reason: str | None = None


class BulkEnrichMetadataUseCase:
    """Enrich all movies and series with external metadata.

    Iterates through all movies and series, enriching those that
    don't yet have metadata (or all if force=True).

    The batch tells a systemic provider failure apart from a per-item
    answer (ADR-038). A "no match" for one title is recorded and the batch
    moves on. Rate limiting the provider would not lift within an item's
    budget, or a streak of provider failures, aborts the run instead of
    turning every remaining item into an error. Items left untouched keep
    no ``tmdb_id``, so the next non-forced run picks them up.

    Args:
        enrich_movie: Use case for single movie enrichment.
        enrich_series: Use case for single series enrichment.
        uow_factory: Factory that opens a fresh media Unit of Work used
            to list the catalog before dispatching to the per-item use
            cases (which each open their own write-scoped UoW).
    """

    #: Time one item may spend waiting on the provider, Retry-After included.
    ITEM_BUDGET_SECONDS: ClassVar[float] = 60.0
    #: Time the whole run may take before it stops and leaves the rest.
    BATCH_BUDGET_SECONDS: ClassVar[float] = 2 * 60 * 60.0
    #: Provider failures in a row that mean "the provider is down, stop".
    MAX_CONSECUTIVE_PROVIDER_FAILURES: ClassVar[int] = 5

    def __init__(
        self,
        enrich_movie: EnrichMovieMetadataUseCase,
        enrich_series: EnrichSeriesMetadataUseCase,
        uow_factory: MediaUnitOfWorkFactory,
    ) -> None:
        self._enrich_movie = enrich_movie
        self._enrich_series = enrich_series
        self._uow_factory = uow_factory

    async def execute(self, input_dto: BulkEnrichInput) -> BulkEnrichOutput:
        """Execute bulk metadata enrichment.

        Args:
            input_dto: Input with force flag.

        Returns:
            Summary of enrichment results, with ``aborted_reason`` set when
            the run stopped early.
        """
        async with self._uow_factory() as uow:
            movies = await uow.movies.list_all()
            all_series = await uow.series.list_all()

        state = _BatchState(started_at=asyncio.get_running_loop().time())

        m_enriched, m_skipped = await self._enrich_all(
            items=[(str(m.id), m.title.value) for m in movies if m.id],
            enrich_fn=self._enrich_movie.execute,
            label="Movie",
            force=input_dto.force,
            state=state,
        )

        s_enriched, s_skipped = 0, 0
        if state.aborted_reason is None:
            s_enriched, s_skipped = await self._enrich_all(
                items=[(str(s.id), s.title.value) for s in all_series if s.id],
                enrich_fn=self._enrich_series.execute,
                label="Series",
                force=input_dto.force,
                state=state,
            )

        if state.aborted_reason is not None:
            state.errors.append(f"Aborted: {state.aborted_reason}")

        return BulkEnrichOutput(
            movies_enriched=m_enriched,
            series_enriched=s_enriched,
            skipped=m_skipped + s_skipped,
            errors=state.errors,
            aborted_reason=state.aborted_reason,
        )

    async def _enrich_all(
        self,
        items: list[tuple[str, str]],
        enrich_fn: Callable[[EnrichMediaInput], Awaitable[EnrichMediaOutput]],
        label: str,
        *,
        force: bool,
        state: _BatchState,
    ) -> tuple[int, int]:
        """Enrich a list of media items until done or until the run aborts."""
        enriched = 0
        skipped = 0
        loop = asyncio.get_running_loop()
        for media_id, title in items:
            if loop.time() - state.started_at >= self.BATCH_BUDGET_SECONDS:
                state.aborted_reason = (
                    f"Batch budget of {self.BATCH_BUDGET_SECONDS:.0f}s exhausted; "
                    "the remaining items are left for the next run"
                )
                break
            try:
                async with deadline(self.ITEM_BUDGET_SECONDS):
                    result = await enrich_fn(EnrichMediaInput(media_id=media_id, force=force))
            except GatewayRateLimitException as e:
                state.aborted_reason = (
                    f"Provider rate limit: retry after {e.retry_after_seconds}s; "
                    "the remaining items are left for the next run"
                )
                break
            except GatewayException as e:
                reason = str(e)
                state.errors.append(f"{label} '{title}': {reason}")
                state.consecutive_provider_failures += 1
                if state.consecutive_provider_failures >= self.MAX_CONSECUTIVE_PROVIDER_FAILURES:
                    state.aborted_reason = (
                        f"{state.consecutive_provider_failures} provider failures in a row "
                        f"(last: {reason}); the remaining items are left for the next run"
                    )
                    break
                continue
            except Exception as e:
                state.errors.append(f"{label} '{title}': {e}")
                continue

            if result.enriched:
                enriched += 1
            elif result.error:
                state.errors.append(f"{label} '{title}': {result.error}")
            else:
                # Skipped without asking the provider: says nothing about
                # its health, so it must not reset the failure streak.
                skipped += 1
                continue
            state.consecutive_provider_failures = 0
        return enriched, skipped


__all__ = ["BulkEnrichMetadataUseCase"]
