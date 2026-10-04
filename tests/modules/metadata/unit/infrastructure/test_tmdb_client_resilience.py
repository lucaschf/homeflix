"""Resilience behaviour of the TMDB ACL: timeouts, Retry-After and retry.

The scenario these tests pin down is a bulk enrichment against a degraded
TMDB: slow responses that trickle bytes, 5xx blips, and ``429`` with a
``Retry-After``. The ACL speaks the provider's protocol (honour
``Retry-After``, cap each call) but only waits or retries inside the time
budget its caller declared with :func:`deadline`. A caller that declares no
budget gets fail-fast behaviour, which is the safe default for interactive
requests.
"""

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from tests.modules.metadata.unit.infrastructure.test_tmdb_client import _movie_details

from src.building_blocks.application.deadline import deadline
from src.building_blocks.infrastructure.errors import (
    GatewayException,
    GatewayRateLimitException,
    GatewayTimeoutException,
    GatewayUnavailableException,
)
from src.building_blocks.infrastructure.retry_after_gate import RetryAfterGate
from src.modules.metadata.infrastructure import tmdb_client as tmdb_module
from src.modules.metadata.infrastructure.tmdb_client import TmdbClient


def _response(status_code: int = 200, headers: dict[str, str] | None = None) -> MagicMock:
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    response.headers = headers or {}
    response.json.return_value = {"id": 1, "title": "Inception", "release_date": "2010-07-16"}
    return response


class _FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class _Harness:
    """A TmdbClient whose HTTP calls, sleeps and gate clock are observable."""

    def __init__(self, responses: list[Any]) -> None:
        self.client = TmdbClient(api_key="test-key")
        self.http = MagicMock()
        self.http.get = AsyncMock(side_effect=responses)
        self.client._client = self.http
        self.clock = _FakeClock()
        self.client._gate = RetryAfterGate(clock=self.clock)
        self.sleeps: list[float] = []

        async def fake_sleep(seconds: float) -> None:
            self.sleeps.append(seconds)
            self.clock.now += seconds

        self.client._sleep = fake_sleep

    @property
    def sends(self) -> int:
        return self.http.get.await_count


@pytest.mark.unit
class TestCallTimeouts:
    """A call has an upper bound even when the provider trickles bytes."""

    def test_http_client_uses_granular_timeouts(self) -> None:
        timeout = TmdbClient(api_key="k")._client.timeout

        assert (timeout.connect, timeout.read, timeout.write, timeout.pool) == (5, 10, 5, 5)

    async def test_a_call_that_never_finishes_is_cut_at_the_total_cap(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(tmdb_module, "_CALL_TOTAL_SECONDS", 0.05)

        async def trickle(*_args: object, **_kwargs: object) -> MagicMock:
            await asyncio.sleep(10)
            return _response()

        harness = _Harness([])
        harness.http.get = AsyncMock(side_effect=trickle)

        with pytest.raises(GatewayTimeoutException):
            await harness.client.get_movie_summary_by_id(1)

    async def test_a_call_is_cut_at_what_is_left_of_the_budget(self) -> None:
        async def trickle(*_args: object, **_kwargs: object) -> MagicMock:
            await asyncio.sleep(10)
            return _response()

        harness = _Harness([])
        harness.http.get = AsyncMock(side_effect=trickle)

        with pytest.raises(GatewayTimeoutException):
            async with deadline(0.05):
                await harness.client.get_movie_summary_by_id(1)

    async def test_nothing_is_sent_once_the_budget_is_spent(self) -> None:
        harness = _Harness([_response(200)])

        with pytest.raises(GatewayTimeoutException):
            async with deadline(0):
                await harness.client.get_movie_summary_by_id(1)

        assert harness.sends == 0


@pytest.mark.unit
class TestRetryAfter:
    """``429`` closes a gate shared by every caller of this client."""

    async def test_waits_for_retry_after_and_resends_inside_the_budget(self) -> None:
        harness = _Harness([_response(429, {"Retry-After": "10"}), _response(200)])

        async with deadline(60):
            result = await harness.client.get_movie_summary_by_id(1)

        assert result is not None
        assert harness.sleeps == [pytest.approx(10)]
        assert harness.sends == 2

    async def test_fails_fast_without_a_declared_budget(self) -> None:
        harness = _Harness([_response(429, {"Retry-After": "10"})])

        with pytest.raises(GatewayRateLimitException) as exc_info:
            await harness.client.get_movie_summary_by_id(1)

        assert exc_info.value.retry_after_seconds == 10
        assert harness.sleeps == []

    async def test_does_not_wait_past_the_budget(self) -> None:
        harness = _Harness([_response(429, {"Retry-After": "120"})])

        with pytest.raises(GatewayRateLimitException):
            async with deadline(30):
                await harness.client.get_movie_summary_by_id(1)

        assert harness.sleeps == []
        assert harness.sends == 1

    async def test_a_closed_gate_stops_other_callers_before_they_send(self) -> None:
        harness = _Harness([_response(429, {"Retry-After": "10"})])
        with pytest.raises(GatewayRateLimitException):
            await harness.client.get_movie_summary_by_id(1)

        with pytest.raises(GatewayRateLimitException) as exc_info:
            await harness.client.get_movie_summary_by_id(2)

        assert harness.sends == 1
        assert exc_info.value.retry_after_seconds == 10

    async def test_a_closed_gate_is_awaited_inside_the_budget(self) -> None:
        harness = _Harness([_response(200)])
        harness.client._gate.close_for(5)

        async with deadline(60):
            await harness.client.get_movie_summary_by_id(1)

        assert harness.sleeps == [pytest.approx(5)]
        assert harness.sends == 1

    async def test_does_not_wait_when_the_call_after_the_wait_would_not_fit(self) -> None:
        """Sleeping 55s of a 60s budget would leave the next call no time at all."""
        harness = _Harness([_response(429, {"Retry-After": "55"})])

        with pytest.raises(GatewayRateLimitException):
            async with deadline(60):
                await harness.client.get_movie_summary_by_id(1)

        assert harness.sleeps == []

    async def test_a_second_429_is_not_retried_again(self) -> None:
        harness = _Harness(
            [_response(429, {"Retry-After": "1"}), _response(429, {"Retry-After": "1"})]
        )

        with pytest.raises(GatewayRateLimitException):
            async with deadline(60):
                await harness.client.get_movie_summary_by_id(1)

        assert harness.sends == 2


@pytest.mark.unit
class TestTransientRetry:
    """One retry with jitter for timeouts and 5xx, only inside the budget."""

    async def test_retries_a_5xx_once_inside_the_budget(self) -> None:
        harness = _Harness([_response(503), _response(200)])

        async with deadline(60):
            result = await harness.client.get_movie_summary_by_id(1)

        assert result is not None
        assert harness.sends == 2
        assert len(harness.sleeps) == 1
        assert 0.5 <= harness.sleeps[0] <= 1.5

    async def test_retries_a_transport_timeout_once_inside_the_budget(self) -> None:
        harness = _Harness([httpx.ReadTimeout("slow"), _response(200)])

        async with deadline(60):
            result = await harness.client.get_movie_summary_by_id(1)

        assert result is not None
        assert harness.sends == 2

    async def test_gives_up_after_the_second_failure(self) -> None:
        harness = _Harness([_response(503), _response(503)])

        with pytest.raises(GatewayUnavailableException):
            async with deadline(60):
                await harness.client.get_movie_summary_by_id(1)

        assert harness.sends == 2

    async def test_does_not_retry_without_a_declared_budget(self) -> None:
        harness = _Harness([httpx.ConnectError("down")])

        with pytest.raises(GatewayUnavailableException):
            await harness.client.get_movie_summary_by_id(1)

        assert harness.sends == 1

    async def test_does_not_retry_when_the_budget_cannot_fit_another_call(self) -> None:
        harness = _Harness([_response(503)])

        with pytest.raises(GatewayUnavailableException):
            async with deadline(3):
                await harness.client.get_movie_summary_by_id(1)

        assert harness.sends == 1

    async def test_never_retries_a_client_error(self) -> None:
        harness = _Harness([_response(401)])

        with pytest.raises(GatewayException):
            async with deadline(60):
                await harness.client.get_movie_summary_by_id(1)

        assert harness.sends == 1

    async def test_a_definitive_not_found_is_returned_without_retry(self) -> None:
        harness = _Harness([_response(404)])

        async with deadline(60):
            result = await harness.client.get_movie_summary_by_id(1)

        assert result is None
        assert harness.sends == 1


@pytest.mark.unit
class TestSpentBudgetIsNotAPartialSuccess:
    """Running out of budget mid-enrichment fails the call; it never drops a locale.

    The translation overlays are best-effort and swallow provider failures.
    If they also swallowed "budget spent", the title would be saved in
    English only, with a ``tmdb_id``, and a non-forced run would never fix it.
    """

    async def test_localized_fetch_fails_when_the_budget_runs_out_before_the_overlay(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        budgets = iter([30.0])
        monkeypatch.setattr(tmdb_module, "remaining_seconds", lambda: next(budgets, 0.0))
        details = _response(200)
        details.json.return_value = _movie_details()
        harness = _Harness([details, _response(200)])

        with pytest.raises(GatewayTimeoutException):
            await harness.client.get_movie_localized(27205)

        assert harness.sends == 1

    async def test_localized_fetch_fails_when_the_budget_runs_out_mid_overlay(self) -> None:
        """An overlay still in flight when the budget expires is not a skipped locale."""
        details = _response(200)
        details.json.return_value = _movie_details()

        async def respond(_url: str, *, params: dict[str, object]) -> MagicMock:
            if params.get("language") not in (None, "en-US"):
                await asyncio.sleep(10)  # the pt-BR overlay hangs
            return details

        harness = _Harness([])
        harness.http.get = AsyncMock(side_effect=respond)

        with pytest.raises(GatewayTimeoutException):
            async with deadline(0.2):
                await harness.client.get_movie_localized(27205)
