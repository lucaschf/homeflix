"""Tests for the provider Retry-After gate."""

import pytest

from src.building_blocks.infrastructure.retry_after_gate import RetryAfterGate


class _FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.mark.unit
class TestRetryAfterGate:
    """The gate remembers until when the provider asked us to stop."""

    def test_starts_open(self) -> None:
        assert RetryAfterGate(clock=_FakeClock()).seconds_until_open() == 0.0

    def test_closing_reports_the_wait(self) -> None:
        clock = _FakeClock()
        gate = RetryAfterGate(clock=clock)

        gate.close_for(10)
        clock.now += 4

        assert gate.seconds_until_open() == pytest.approx(6)

    def test_reopens_after_the_wait(self) -> None:
        clock = _FakeClock()
        gate = RetryAfterGate(clock=clock)

        gate.close_for(10)
        clock.now += 11

        assert gate.seconds_until_open() == 0.0

    def test_a_shorter_closure_never_reopens_the_gate_early(self) -> None:
        clock = _FakeClock()
        gate = RetryAfterGate(clock=clock)

        gate.close_for(30)
        gate.close_for(5)

        assert gate.seconds_until_open() == pytest.approx(30)
