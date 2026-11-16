"""Tests for WatchProgress entity."""

from src.modules.watch_progress.domain.entities import WatchProgress
from src.modules.watch_progress.domain.events import WatchCompletedEvent
from src.modules.watch_progress.domain.value_objects import (
    SubtitlePreference,
    WatchableMediaId,
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


class TestWatchProgressCompletionEvent:
    """Finishing a title raises ``WatchCompletedEvent`` once, on the transition.

    Collections removes a finished movie from the profile's watchlist off
    this event, so it must not fire again while the profile rewatches it.
    """

    def test_update_into_completion_raises_the_event(self):
        progress = _create_progress(position_seconds=1800)

        completed = progress.update_position(6600)

        events = completed.pull_events()
        assert len(events) == 1
        assert isinstance(events[0], WatchCompletedEvent)
        assert events[0].profile_id == _PROFILE_ID
        assert events[0].media_id == WatchableMediaId("mov_abc123def456")

    def test_update_below_the_threshold_raises_nothing(self):
        progress = _create_progress(position_seconds=1800)

        assert progress.update_position(3600).pull_events() == []

    def test_update_of_a_completed_title_raises_nothing(self):
        completed = _create_progress(position_seconds=6600)
        completed.pull_events()

        rewatched = completed.update_position(6700)

        assert rewatched.pull_events() == []

    def test_create_already_completed_raises_the_event(self):
        progress = _create_progress(position_seconds=6600)

        events = progress.pull_events()
        assert len(events) == 1
        assert isinstance(events[0], WatchCompletedEvent)
        assert events[0].media_id == WatchableMediaId("mov_abc123def456")

    def test_create_in_progress_raises_nothing(self):
        assert _create_progress(position_seconds=1800).pull_events() == []

    def test_episode_completion_raises_the_event(self):
        progress = _create_progress(
            media_id="epi_ser_abc123def456_1_2",
            media_type=WatchableMediaType.EPISODE,
            position_seconds=300,
            duration_seconds=2700,
        )

        events = progress.update_position(2600).pull_events()

        assert [event.media_id for event in events] == [
            WatchableMediaId("epi_ser_abc123def456_1_2")
        ]
