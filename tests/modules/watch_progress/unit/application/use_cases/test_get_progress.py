"""Tests for GetProgressUseCase."""

import pytest

from src.modules.watch_progress.application.dtos import GetProgressInput, ProgressOutput
from src.modules.watch_progress.application.use_cases import GetProgressUseCase
from src.modules.watch_progress.domain.entities import WatchProgress
from src.modules.watch_progress.domain.value_objects import WatchableMediaId, WatchableMediaType
from src.shared_kernel.value_objects.profile_id import ProfileId
from tests.modules.watch_progress.unit.conftest import make_watch_progress_uow_mock

_PROFILE_ID = ProfileId("prf_test12345678")


class TestGetProgressUseCase:
    """Tests for GetProgressUseCase."""

    @pytest.mark.asyncio
    async def test_returns_progress_when_found(self):
        existing = WatchProgress.create(
            profile_id=_PROFILE_ID,
            media_id="mov_abc123def456",
            media_type=WatchableMediaType.MOVIE,
            position_seconds=1800,
            duration_seconds=7200,
        )
        mocks = make_watch_progress_uow_mock()
        mocks.progress.find_by_media_id.return_value = existing
        use_case = GetProgressUseCase(uow_factory=mocks.factory)

        result = await use_case.execute(
            GetProgressInput(
                profile_id=_PROFILE_ID.value,
                media_id="mov_abc123def456",
            )
        )

        assert isinstance(result, ProgressOutput)
        assert result.position_seconds == 1800
        assert result.percentage == 25.0
        mocks.progress.find_by_media_id.assert_called_once_with(
            WatchableMediaId("mov_abc123def456"), _PROFILE_ID
        )

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self):
        mocks = make_watch_progress_uow_mock()
        mocks.progress.find_by_media_id.return_value = None
        use_case = GetProgressUseCase(uow_factory=mocks.factory)

        result = await use_case.execute(
            GetProgressInput(
                profile_id=_PROFILE_ID.value,
                media_id="mov_abc123def456",
            )
        )

        assert result is None
