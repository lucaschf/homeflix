"""Tests for the manual subtitle-OCR trigger's single-flight guard."""

import asyncio
from unittest.mock import MagicMock

import pytest

from src.modules.streaming.presentation.routes import admin_subtitle_ocr_routes as mod


async def _drain() -> None:
    """Wait for all in-flight manual-OCR tasks to finish."""
    while mod._manual_ocr_tasks:
        await asyncio.gather(*list(mod._manual_ocr_tasks), return_exceptions=True)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_single_flight_ignores_repeat_trigger_for_same_title() -> None:
    gate = asyncio.Event()

    async def _slow_execute(_input: object) -> None:
        await gate.wait()

    use_case = MagicMock()
    use_case.execute = _slow_execute

    try:
        # first trigger starts a run
        assert mod._fire_manual_ocr(use_case, "movie", "mov_aaaaaaaaaaaa") is True
        # repeat while still running is ignored
        assert mod._fire_manual_ocr(use_case, "movie", "mov_aaaaaaaaaaaa") is False
        # a different title still starts
        assert mod._fire_manual_ocr(use_case, "movie", "mov_bbbbbbbbbbbb") is True

        gate.set()
        await _drain()

        # once finished, the same title can be triggered again
        assert mod._fire_manual_ocr(use_case, "movie", "mov_aaaaaaaaaaaa") is True
        await _drain()
    finally:
        gate.set()
        await _drain()
        mod._inflight_media.clear()
