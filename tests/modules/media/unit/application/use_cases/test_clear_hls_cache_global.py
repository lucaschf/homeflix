"""Tests for ClearHlsCacheGlobalUseCase."""

from unittest.mock import MagicMock

import pytest

from src.modules.streaming.application.ports.hls_playlist_port import HlsPlaylistPort
from src.modules.streaming.application.use_cases.clear_hls_cache_global import (
    ClearHlsCacheGlobalUseCase,
)


@pytest.mark.unit
class TestClearHlsCacheGlobalUseCase:
    def test_should_delegate_global_clear_to_port(self) -> None:
        hls = MagicMock(spec=HlsPlaylistPort)
        use_case = ClearHlsCacheGlobalUseCase(hls=hls)

        use_case.execute()

        hls.clear_cache.assert_called_once_with(None)
