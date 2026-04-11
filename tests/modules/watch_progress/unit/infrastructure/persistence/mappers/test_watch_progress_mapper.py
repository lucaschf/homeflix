"""Unit tests for WatchProgressMapper."""

from datetime import UTC, datetime

import pytest

from src.modules.watch_progress.domain.entities import WatchProgress
from src.modules.watch_progress.domain.value_objects import ProgressId
from src.modules.watch_progress.infrastructure.persistence.mappers import (
    WatchProgressMapper,
)
from src.modules.watch_progress.infrastructure.persistence.models import (
    WatchProgressModel,
)


def _make_progress(
    media_id: str = "mov_abc123def456",
    media_type: str = "movie",
    position: int = 1800,
    duration: int = 7200,
    progress_id: ProgressId | None = None,
) -> WatchProgress:
    return WatchProgress(
        id=progress_id or ProgressId.generate(),
        media_id=media_id,
        media_type=media_type,
        position_seconds=position,
        duration_seconds=duration,
    )


@pytest.mark.unit
class TestWatchProgressMapperToModel:
    """Tests for WatchProgressMapper.to_model."""

    def test_should_raise_when_id_is_none(self) -> None:
        progress = WatchProgress(
            id=None,
            media_id="mov_abc123def456",
            media_type="movie",
            position_seconds=100,
            duration_seconds=7200,
        )

        with pytest.raises(ValueError, match="Cannot map entity without ID"):
            WatchProgressMapper.to_model(progress)

    def test_should_convert_entity_correctly(self) -> None:
        progress_id = ProgressId.generate()
        progress = _make_progress(progress_id=progress_id)

        model = WatchProgressMapper.to_model(progress)

        assert model.external_id == str(progress_id)
        assert model.media_id == "mov_abc123def456"
        assert model.media_type == "movie"
        assert model.position_seconds == 1800
        assert model.duration_seconds == 7200
        assert model.status == "in_progress"

    def test_should_preserve_optional_tracks(self) -> None:
        progress = WatchProgress(
            id=ProgressId.generate(),
            media_id="mov_abc123def456",
            media_type="movie",
            position_seconds=100,
            duration_seconds=7200,
            audio_track=1,
            subtitle_track=2,
        )

        model = WatchProgressMapper.to_model(progress)

        assert model.audio_track == 1
        assert model.subtitle_track == 2

    def test_should_preserve_completed_status(self) -> None:
        now = datetime.now(UTC)
        progress = WatchProgress(
            id=ProgressId.generate(),
            media_id="mov_abc123def456",
            media_type="movie",
            position_seconds=7200,
            duration_seconds=7200,
            status="completed",
            completed_at=now,
        )

        model = WatchProgressMapper.to_model(progress)

        assert model.status == "completed"
        assert model.completed_at == now


@pytest.mark.unit
class TestWatchProgressMapperToEntity:
    """Tests for WatchProgressMapper.to_entity."""

    def test_should_convert_model_correctly(self) -> None:
        progress_id = ProgressId.generate()
        now = datetime.now(UTC)
        model = WatchProgressModel(
            external_id=str(progress_id),
            media_id="epi_xyz789abc123",
            media_type="episode",
            position_seconds=900,
            duration_seconds=3600,
            status="in_progress",
            audio_track=0,
            subtitle_track=1,
            last_watched_at=now,
            completed_at=None,
        )
        model.created_at = now
        model.updated_at = now

        entity = WatchProgressMapper.to_entity(model)

        assert entity.id == progress_id
        assert entity.media_id == "epi_xyz789abc123"
        assert entity.media_type == "episode"
        assert entity.position_seconds == 900
        assert entity.status == "in_progress"
        assert entity.audio_track == 0
        assert entity.subtitle_track == 1

    def test_round_trip_should_preserve_fields(self) -> None:
        progress_id = ProgressId.generate()
        original = _make_progress(progress_id=progress_id)

        model = WatchProgressMapper.to_model(original)
        model.created_at = original.created_at
        model.updated_at = original.updated_at
        result = WatchProgressMapper.to_entity(model)

        assert result.id == original.id
        assert result.media_id == original.media_id
        assert result.position_seconds == original.position_seconds
        assert result.duration_seconds == original.duration_seconds


@pytest.mark.unit
class TestWatchProgressMapperUpdateModel:
    """Tests for WatchProgressMapper.update_model."""

    def test_should_update_mutable_fields(self) -> None:
        progress_id = ProgressId.generate()
        now = datetime.now(UTC)
        model = WatchProgressModel(
            external_id=str(progress_id),
            media_id="mov_abc123def456",
            media_type="movie",
            position_seconds=100,
            duration_seconds=7200,
            status="in_progress",
            audio_track=None,
            subtitle_track=None,
            last_watched_at=now,
            completed_at=None,
        )

        later = datetime.now(UTC)
        updated = WatchProgress(
            id=progress_id,
            media_id="mov_abc123def456",
            media_type="movie",
            position_seconds=6500,
            duration_seconds=7200,
            status="completed",
            audio_track=1,
            subtitle_track=2,
            last_watched_at=later,
            completed_at=later,
        )

        result = WatchProgressMapper.update_model(model, updated)

        assert result.position_seconds == 6500
        assert result.status == "completed"
        assert result.audio_track == 1
        assert result.subtitle_track == 2
        assert result.last_watched_at == later
        assert result.completed_at == later

    def test_should_not_change_external_id_or_media_id(self) -> None:
        progress_id = ProgressId.generate()
        model = WatchProgressModel(
            external_id=str(progress_id),
            media_id="mov_original00000",
            media_type="movie",
            position_seconds=100,
            duration_seconds=7200,
            status="in_progress",
            last_watched_at=datetime.now(UTC),
        )

        updated = WatchProgress(
            id=progress_id,
            media_id="mov_different000",
            media_type="movie",
            position_seconds=200,
            duration_seconds=7200,
        )

        result = WatchProgressMapper.update_model(model, updated)

        # media_id and external_id are not touched by update_model
        assert result.external_id == str(progress_id)
        assert result.media_id == "mov_original00000"
