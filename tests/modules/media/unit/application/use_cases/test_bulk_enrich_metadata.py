"""Tests for BulkEnrichMetadataUseCase under a degraded provider (ADR-038).

Before ADR-038, one ``429`` turned every remaining item into an error in a
few seconds and the run still finished as "succeeded". The batch now tells a
systemic provider failure apart from a per-item answer: it aborts on rate
limiting or on a streak of transient failures and leaves the untouched items
without ``tmdb_id``, so the next run picks them up.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.building_blocks.application.deadline import remaining_seconds
from src.building_blocks.infrastructure.errors import (
    GatewayRateLimitException,
    GatewayTimeoutException,
)
from src.modules.media.application.dtos.enrichment_dtos import (
    BulkEnrichInput,
    EnrichMediaInput,
    EnrichMediaOutput,
)
from src.modules.media.application.use_cases.bulk_enrich_metadata import (
    BulkEnrichMetadataUseCase,
)
from src.modules.media.domain.entities import Movie, Series
from tests.modules.media.unit.conftest import make_media_uow_mock

_LIBRARY_ID = "lib_test12345678"


def _movies(count: int) -> list[Movie]:
    return [
        Movie.create(
            library_id=_LIBRARY_ID,
            title=f"Movie {index}",
            year=2000 + index,
            duration=0,
            file_path=f"/movies/movie-{index}.mkv",
            file_size=1,
            resolution="1080p",
        )
        for index in range(count)
    ]


def _rate_limited() -> GatewayRateLimitException:
    return GatewayRateLimitException(
        message="TMDB rate limit exceeded", gateway_name="TMDB", retry_after_seconds=120
    )


def _timed_out() -> GatewayTimeoutException:
    return GatewayTimeoutException(message="TMDB request timed out", gateway_name="TMDB")


def _ok(media_id: str = "x") -> EnrichMediaOutput:
    return EnrichMediaOutput(media_id=media_id, enriched=True, provider="tmdb")


def _build(
    movie_outcomes: list[object],
    movie_count: int,
    series: list[Series] | None = None,
) -> tuple[BulkEnrichMetadataUseCase, MagicMock, MagicMock]:
    mocks = make_media_uow_mock()
    mocks.movies.list_all.return_value = _movies(movie_count)
    mocks.series.list_all.return_value = series or []
    enrich_movie = MagicMock()
    enrich_movie.execute = AsyncMock(side_effect=movie_outcomes)
    enrich_series = MagicMock()
    enrich_series.execute = AsyncMock(return_value=_ok())
    use_case = BulkEnrichMetadataUseCase(
        enrich_movie=enrich_movie,
        enrich_series=enrich_series,
        uow_factory=mocks.factory,
    )
    return use_case, enrich_movie, enrich_series


@pytest.mark.unit
class TestBulkEnrichUnderDegradedProvider:
    async def test_rate_limit_aborts_the_batch_instead_of_burning_it(self) -> None:
        use_case, enrich_movie, _ = _build([_ok(), _rate_limited(), _ok(), _ok()], movie_count=4)

        output = await use_case.execute(BulkEnrichInput())

        assert enrich_movie.execute.await_count == 2
        assert output.movies_enriched == 1
        assert output.aborted_reason is not None
        assert "rate limit" in output.aborted_reason.lower()
        assert output.errors[-1].startswith("Aborted:")
        assert "120" in output.aborted_reason

    async def test_abort_stops_series_too(self) -> None:
        series = [Series.create(library_id=_LIBRARY_ID, title="Breaking Bad", start_year=2008)]
        use_case, _, enrich_series = _build([_rate_limited()], movie_count=1, series=series)

        await use_case.execute(BulkEnrichInput())

        enrich_series.execute.assert_not_awaited()

    async def test_a_streak_of_transient_failures_trips_the_breaker(self) -> None:
        outcomes: list[object] = [_timed_out()] * 10
        use_case, enrich_movie, _ = _build(outcomes, movie_count=10)

        output = await use_case.execute(BulkEnrichInput())

        limit = BulkEnrichMetadataUseCase.MAX_CONSECUTIVE_PROVIDER_FAILURES
        assert enrich_movie.execute.await_count == limit
        assert output.aborted_reason is not None
        assert len(output.errors) >= limit

    async def test_a_success_resets_the_transient_streak(self) -> None:
        limit = BulkEnrichMetadataUseCase.MAX_CONSECUTIVE_PROVIDER_FAILURES
        outcomes: list[object] = [
            *[_timed_out()] * (limit - 1),
            _ok(),
            *[_timed_out()] * (limit - 1),
        ]
        use_case, enrich_movie, _ = _build(outcomes, movie_count=len(outcomes))

        output = await use_case.execute(BulkEnrichInput())

        assert enrich_movie.execute.await_count == len(outcomes)
        assert output.aborted_reason is None

    async def test_skipped_items_do_not_reset_the_failure_streak(self) -> None:
        """An already-enriched item never asked the provider; it proves nothing."""
        limit = BulkEnrichMetadataUseCase.MAX_CONSECUTIVE_PROVIDER_FAILURES
        skipped = EnrichMediaOutput(media_id="x", enriched=False)
        outcomes: list[object] = []
        for _ in range(limit):
            outcomes += [_timed_out(), skipped]
        use_case, _, _ = _build(outcomes, movie_count=len(outcomes))

        output = await use_case.execute(BulkEnrichInput())

        assert output.aborted_reason is not None

    async def test_a_non_provider_error_is_recorded_without_tripping_the_breaker(self) -> None:
        """A database timeout is not the provider's fault and must not be blamed on it."""
        limit = BulkEnrichMetadataUseCase.MAX_CONSECUTIVE_PROVIDER_FAILURES
        use_case, enrich_movie, _ = _build(
            [TimeoutError("db")] * (limit + 2), movie_count=limit + 2
        )

        output = await use_case.execute(BulkEnrichInput())

        assert enrich_movie.execute.await_count == limit + 2
        assert output.aborted_reason is None
        assert len(output.errors) == limit + 2

    async def test_a_definitive_miss_keeps_the_batch_going(self) -> None:
        miss = EnrichMediaOutput(media_id="x", enriched=False, error="No metadata found")
        use_case, enrich_movie, _ = _build([miss] * 8, movie_count=8)

        output = await use_case.execute(BulkEnrichInput())

        assert enrich_movie.execute.await_count == 8
        assert output.aborted_reason is None
        assert len(output.errors) == 8

    async def test_each_item_runs_under_a_declared_budget(self) -> None:
        budgets: list[float | None] = []

        async def enrich(_input: EnrichMediaInput) -> EnrichMediaOutput:
            budgets.append(remaining_seconds())
            return _ok()

        use_case, enrich_movie, _ = _build([], movie_count=2)
        enrich_movie.execute.side_effect = enrich

        await use_case.execute(BulkEnrichInput())

        assert len(budgets) == 2
        budget = BulkEnrichMetadataUseCase.ITEM_BUDGET_SECONDS
        assert all(b is not None and 0 < b <= budget for b in budgets)

    async def test_the_batch_budget_stops_the_run(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(BulkEnrichMetadataUseCase, "BATCH_BUDGET_SECONDS", 0.0)
        use_case, enrich_movie, _ = _build([_ok()], movie_count=1)

        output = await use_case.execute(BulkEnrichInput())

        enrich_movie.execute.assert_not_awaited()
        assert output.aborted_reason is not None
