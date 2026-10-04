"""Tests for the ambient call deadline."""

import asyncio

import pytest

from src.building_blocks.application.deadline import deadline, remaining_seconds


@pytest.mark.unit
class TestDeadline:
    """A caller declares how long it tolerates; I/O code reads what is left."""

    async def test_no_deadline_outside_a_scope(self) -> None:
        assert remaining_seconds() is None

    async def test_remaining_reflects_the_declared_budget(self) -> None:
        async with deadline(30):
            remaining = remaining_seconds()

        assert remaining is not None
        assert 29 < remaining <= 30

    async def test_scope_is_cleared_on_exit(self) -> None:
        async with deadline(30):
            pass

        assert remaining_seconds() is None

    async def test_nested_scope_cannot_extend_the_outer_budget(self) -> None:
        async with deadline(5), deadline(60):
            remaining = remaining_seconds()

        assert remaining is not None
        assert remaining <= 5

    async def test_nested_scope_can_shorten_the_budget(self) -> None:
        async with deadline(60), deadline(5):
            remaining = remaining_seconds()

        assert remaining is not None
        assert remaining <= 5

    async def test_the_budget_never_cancels_work(self) -> None:
        """Local work past the budget completes; only remote waits are bounded."""
        async with deadline(0.01):
            await asyncio.sleep(0.03)
            remaining = remaining_seconds()

        assert remaining == 0.0
