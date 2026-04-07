"""Tests for WatchProgress entity."""


from src.modules.watch_progress.domain.entities import WatchProgress


class TestWatchProgress:
    """Tests for WatchProgress entity."""

    def test_create_sets_in_progress_status(self):
        progress = WatchProgress.create(
            media_id="mov_abc123def456",
            media_type="movie",
            position_seconds=1800,
            duration_seconds=7200,
        )
        assert progress.status == "in_progress"
        assert progress.id is not None
        assert str(progress.id).startswith("prg_")

    def test_create_auto_completes_at_90_percent(self):
        progress = WatchProgress.create(
            media_id="mov_abc123def456",
            media_type="movie",
            position_seconds=6500,
            duration_seconds=7200,
        )
        assert progress.status == "completed"
        assert progress.completed_at is not None

    def test_percentage_calculation(self):
        progress = WatchProgress.create(
            media_id="mov_abc123def456",
            media_type="movie",
            position_seconds=3600,
            duration_seconds=7200,
        )
        assert progress.percentage == 50.0

    def test_percentage_zero_position(self):
        progress = WatchProgress.create(
            media_id="mov_abc123def456",
            media_type="movie",
            position_seconds=0,
            duration_seconds=7200,
        )
        assert progress.percentage == 0.0

    def test_percentage_capped_at_100(self):
        progress = WatchProgress.create(
            media_id="mov_abc123def456",
            media_type="movie",
            position_seconds=8000,
            duration_seconds=7200,
        )
        assert progress.percentage == 100.0

    def test_update_position_preserves_identity(self):
        progress = WatchProgress.create(
            media_id="mov_abc123def456",
            media_type="movie",
            position_seconds=100,
            duration_seconds=7200,
        )
        updated = progress.update_position(200)
        assert updated.position_seconds == 200
        assert updated.id == progress.id
        assert updated.media_id == progress.media_id

    def test_update_position_auto_completes(self):
        progress = WatchProgress.create(
            media_id="mov_abc123def456",
            media_type="movie",
            position_seconds=100,
            duration_seconds=7200,
        )
        assert progress.status == "in_progress"

        updated = progress.update_position(6600)
        assert updated.status == "completed"
        assert updated.completed_at is not None

    def test_update_position_saves_audio_track(self):
        progress = WatchProgress.create(
            media_id="mov_abc123def456",
            media_type="movie",
            position_seconds=100,
            duration_seconds=7200,
        )
        updated = progress.update_position(200, audio_track=2)
        assert updated.audio_track == 2

    def test_update_position_saves_subtitle_track(self):
        progress = WatchProgress.create(
            media_id="mov_abc123def456",
            media_type="movie",
            position_seconds=100,
            duration_seconds=7200,
        )
        updated = progress.update_position(200, subtitle_track=1)
        assert updated.subtitle_track == 1

    def test_is_completed_property(self):
        progress = WatchProgress.create(
            media_id="mov_abc123def456",
            media_type="movie",
            position_seconds=100,
            duration_seconds=7200,
        )
        assert not progress.is_completed

        completed = progress.update_position(6600)
        assert completed.is_completed

    def test_create_with_episode(self):
        progress = WatchProgress.create(
            media_id="epi_abc123def456",
            media_type="episode",
            position_seconds=300,
            duration_seconds=2700,
        )
        assert progress.media_type == "episode"
        assert progress.media_id == "epi_abc123def456"
