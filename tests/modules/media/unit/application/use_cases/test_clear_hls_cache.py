"""Tests for ClearHlsCacheUseCase."""

from unittest.mock import MagicMock

import pytest

from src.modules.streaming.application.ports.hls_playlist_port import HlsPlaylistPort
from src.modules.streaming.application.use_cases.clear_hls_cache import (
    ClearHlsCacheInput,
    ClearHlsCacheUseCase,
)


@pytest.mark.unit
class TestClearHlsCacheUseCase:
    @pytest.mark.asyncio
    async def test_should_delegate_to_port_when_path_present(self) -> None:
        hls = MagicMock(spec=HlsPlaylistPort)
        use_case = ClearHlsCacheUseCase(hls=hls)

        await use_case.execute(ClearHlsCacheInput(file_path="/movies/a.mkv"))

        hls.clear_cache.assert_called_once_with("/movies/a.mkv")

    @pytest.mark.asyncio
    async def test_should_be_noop_when_path_is_none(self) -> None:
        hls = MagicMock(spec=HlsPlaylistPort)
        use_case = ClearHlsCacheUseCase(hls=hls)

        await use_case.execute(ClearHlsCacheInput(file_path=None))

        hls.clear_cache.assert_not_called()
