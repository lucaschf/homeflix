"""Tests for WatchProgress entity."""

from src.modules.watch_progress.domain.entities import WatchProgress
from src.modules.watch_progress.domain.value_objects import (
    SubtitlePreference,
    WatchableMediaType,
)
from src.shared_kernel.value_objects.profile_id import ProfileId

_PROFILE_ID = ProfileId("prf_test12345678")


def _create_progress(
    *,
    media_id: str = "mov_abc123def456",
    media_type: WatchableMediaType = WatchableMediaType.MOVIE,
    position_seconds: int = 100,
    duration_seconds: int = 7200,
    audio_track: int | None = None,
    subtitle_track: SubtitlePreference | None = None,
) -> WatchProgress:
    return WatchProgress.create(
        profile_id=_PROFILE_ID,
        media_id=media_id,
        media_type=media_type,
        position_seconds=position_seconds,
        duration_seconds=duration_seconds,
        audio_track=audio_track,
        subtitle_track=subtitle_track,
    )


class TestWatchProgress:
    """Tests for WatchProgress entity."""

    def test_create_sets_in_progress_status(self):
        progress = _create_progress(position_seconds=1800)
        assert progress.status == "in_progress"
        assert progress.id is not None
        assert str(progress.id).startswith("prg_")
        assert progress.profile_id == _PROFILE_ID

    def test_create_auto_completes_at_90_percent(self):
        progress = _create_progress(position_seconds=6500)
        assert progress.status == "completed"
        assert progress.completed_at is not None

    def test_percentage_calculation(self):
        progress = _create_progress(position_seconds=3600)
        assert progress.percentage == 50.0

    def test_percentage_zero_position(self):
        progress = _create_progress(position_seconds=0)
        assert progress.percentage == 0.0

    def test_percentage_capped_at_100(self):
        progress = _create_progress(position_seconds=8000)
        assert progress.percentage == 100.0

    def test_update_position_preserves_identity(self):
        progress = _create_progress()
        updated = progress.update_position(200)
        assert updated.position_seconds == 200
        assert updated.id == progress.id
        assert updated.media_id == progress.media_id
        assert updated.profile_id == progress.profile_id

    def test_update_position_auto_completes(self):
        progress = _create_progress()
        assert progress.status == "in_progress"

        updated = progress.update_position(6600)
        assert updated.status == "completed"
        assert updated.completed_at is not None

    def test_update_position_saves_audio_track(self):
        progress = _create_progress()
        updated = progress.update_position(200, audio_track=2)
        assert updated.audio_track == 2

    def test_update_position_saves_subtitle_track(self):
        progress = _create_progress()
        updated = progress.update_position(200, subtitle_track=SubtitlePreference.track(1))
        assert updated.subtitle_track == SubtitlePreference.track(1)

    def test_update_position_saves_subtitles_off(self):
        progress = _create_progress()
        updated = progress.update_position(200, subtitle_track=SubtitlePreference.off())
        assert updated.subtitle_track is not None
        assert updated.subtitle_track.is_off

    def test_is_completed_property(self):
        progress = _create_progress()
        assert not progress.is_completed

        completed = progress.update_position(6600)
        assert completed.is_completed

    def test_create_with_episode(self):
        progress = _create_progress(
            media_id="epi_ser_abc123def456_1_2",
            media_type=WatchableMediaType.EPISODE,
            position_seconds=300,
            duration_seconds=2700,
        )
        assert progress.media_type == "episode"
        assert progress.media_id.value == "epi_ser_abc123def456_1_2"
