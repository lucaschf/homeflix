"""Tests for SaveProgressUseCase."""

from unittest.mock import AsyncMock

import pytest

from src.modules.watch_progress.application.dtos import ProgressOutput, SaveProgressInput
from src.modules.watch_progress.application.use_cases import SaveProgressUseCase
from src.modules.watch_progress.domain.entities import WatchProgress
from src.modules.watch_progress.domain.repositories import WatchProgressRepository


class TestSaveProgressUseCase:
    """Tests for SaveProgressUseCase."""

    @pytest.mark.asyncio
    async def test_creates_new_progress_when_none_exists(self):
        mock_repo = AsyncMock(spec=WatchProgressRepository)
        mock_repo.find_by_media_id.return_value = None
        mock_repo.save.side_effect = lambda p: p
        use_case = SaveProgressUseCase(progress_repository=mock_repo)

        result = await use_case.execute(
            SaveProgressInput(
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

    @pytest.mark.asyncio
    async def test_updates_existing_progress(self):
        existing = WatchProgress.create(
            media_id="mov_abc123def456",
            media_type="movie",
            position_seconds=1000,
            duration_seconds=7200,
        )
        mock_repo = AsyncMock(spec=WatchProgressRepository)
        mock_repo.find_by_media_id.return_value = existing
        mock_repo.save.side_effect = lambda p: p
        use_case = SaveProgressUseCase(progress_repository=mock_repo)

        result = await use_case.execute(
            SaveProgressInput(
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
        mock_repo = AsyncMock(spec=WatchProgressRepository)
        mock_repo.find_by_media_id.return_value = None
        mock_repo.save.side_effect = lambda p: p
        use_case = SaveProgressUseCase(progress_repository=mock_repo)

        result = await use_case.execute(
            SaveProgressInput(
                media_id="mov_abc123def456",
                media_type="movie",
                position_seconds=6500,
                duration_seconds=7200,
            )
        )

        assert result.status == "completed"

    @pytest.mark.asyncio
    async def test_saves_audio_and_subtitle_track(self):
        mock_repo = AsyncMock(spec=WatchProgressRepository)
        mock_repo.find_by_media_id.return_value = None
        mock_repo.save.side_effect = lambda p: p
        use_case = SaveProgressUseCase(progress_repository=mock_repo)

        result = await use_case.execute(
            SaveProgressInput(
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
