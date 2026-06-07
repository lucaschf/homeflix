"""Tests for SaveProgressUseCase."""

import pytest

from src.modules.watch_progress.application.dtos import ProgressOutput, SaveProgressInput
from src.modules.watch_progress.application.use_cases import SaveProgressUseCase
from src.modules.watch_progress.domain.entities import WatchProgress
from src.modules.watch_progress.domain.value_objects import WatchableMediaId, WatchableMediaType
from src.shared_kernel.value_objects.profile_id import ProfileId
from tests.modules.watch_progress.unit.conftest import make_watch_progress_uow_mock

_PROFILE_ID = ProfileId("prf_test12345678")


class TestSaveProgressUseCase:
    """Tests for SaveProgressUseCase."""

    @pytest.mark.asyncio
    async def test_creates_new_progress_when_none_exists(self):
        mocks = make_watch_progress_uow_mock()
        mock_repo = mocks.progress
        mock_repo.find_by_media_id.return_value = None
        mock_repo.save.side_effect = lambda p: p
        use_case = SaveProgressUseCase(uow_factory=mocks.factory)

        result = await use_case.execute(
            SaveProgressInput(
                profile_id=_PROFILE_ID.value,
                media_id="mov_abc123def456",
                media_type="movie",
                position_seconds=1800,
                duration_seconds=7200,
            )
        )

        assert isinstance(result, ProgressOutput)
        assert result.media_id == "mov_abc123def456"
        assert result.position_seconds == 1800
        assert result.status == "in_progress"
        mock_repo.save.assert_called_once()
        # The repo find lookup was scoped by profile.
        mock_repo.find_by_media_id.assert_called_once_with(
            WatchableMediaId("mov_abc123def456"), _PROFILE_ID
        )

    @pytest.mark.asyncio
    async def test_updates_existing_progress(self):
        existing = WatchProgress.create(
            profile_id=_PROFILE_ID,
            media_id="mov_abc123def456",
            media_type=WatchableMediaType.MOVIE,
            position_seconds=1000,
            duration_seconds=7200,
        )
        mocks = make_watch_progress_uow_mock()
        mock_repo = mocks.progress
        mock_repo.find_by_media_id.return_value = existing
        mock_repo.save.side_effect = lambda p: p
        use_case = SaveProgressUseCase(uow_factory=mocks.factory)

        result = await use_case.execute(
            SaveProgressInput(
                profile_id=_PROFILE_ID.value,
                media_id="mov_abc123def456",
                media_type="movie",
                position_seconds=3600,
                duration_seconds=7200,
            )
        )

        assert result.position_seconds == 3600
        assert result.percentage == 50.0

    @pytest.mark.asyncio
    async def test_auto_completes_at_90_percent(self):
        mocks = make_watch_progress_uow_mock()
        mock_repo = mocks.progress
        mock_repo.find_by_media_id.return_value = None
        mock_repo.save.side_effect = lambda p: p
        use_case = SaveProgressUseCase(uow_factory=mocks.factory)

        result = await use_case.execute(
            SaveProgressInput(
                profile_id=_PROFILE_ID.value,
                media_id="mov_abc123def456",
                media_type="movie",
                position_seconds=6500,
                duration_seconds=7200,
            )
        )

        assert result.status == "completed"

    @pytest.mark.asyncio
    async def test_saves_audio_and_subtitle_track(self):
        mocks = make_watch_progress_uow_mock()
        mock_repo = mocks.progress
        mock_repo.find_by_media_id.return_value = None
        mock_repo.save.side_effect = lambda p: p
        use_case = SaveProgressUseCase(uow_factory=mocks.factory)

        result = await use_case.execute(
            SaveProgressInput(
                profile_id=_PROFILE_ID.value,
                media_id="mov_abc123def456",
                media_type="movie",
                position_seconds=100,
                duration_seconds=7200,
                audio_track=2,
                subtitle_track=1,
            )
        )

        assert result.audio_track == 2
        assert result.subtitle_track == 1
