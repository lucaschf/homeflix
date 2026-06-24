"""Tests for the in-memory now-playing registry."""

import pytest

from src.modules.media.infrastructure.streaming.now_playing_registry import (
    NowPlayingRegistry,
)


@pytest.mark.unit
def test_empty_registry_has_no_sessions() -> None:
    assert NowPlayingRegistry().active() == []


@pytest.mark.unit
def test_note_view_and_segment_surface_a_live_session() -> None:
    registry = NowPlayingRegistry()
    registry.note_view(
        "h1",
        profile_id="prf_1",
        media_id="mov_1",
        media_kind="movie",
        title="Inception",
        year=2010,
        duration_seconds=1000,
    )
    registry.note_segment("h1", byte_count=5_000_000, segment_index=3)

    sessions = registry.active()

    assert len(sessions) == 1
    session = sessions[0]
    assert session.title == "Inception"
    assert session.profile_id == "prf_1"
    assert session.position_seconds == 30  # segment 3 x 10s
    assert session.duration_seconds == 1000
    assert session.mbps > 0


@pytest.mark.unit
def test_position_is_clamped_to_duration() -> None:
    registry = NowPlayingRegistry()
    registry.note_view("h", media_id="m", duration_seconds=25)
    registry.note_segment("h", byte_count=1, segment_index=100)

    assert registry.active()[0].position_seconds == 25


@pytest.mark.unit
def test_start_offset_is_added_to_position() -> None:
    registry = NowPlayingRegistry()
    registry.note_view("h", media_id="m", duration_seconds=10_000, start_offset=300)
    registry.note_segment("h", byte_count=1, segment_index=2)

    assert registry.active()[0].position_seconds == 320  # 300 + 2 x 10s


@pytest.mark.unit
def test_separate_path_hashes_are_separate_sessions() -> None:
    registry = NowPlayingRegistry()
    registry.note_view("a", media_id="a", title="A", duration_seconds=100)
    registry.note_view("b", media_id="b", title="B", duration_seconds=100)

    assert {s.title for s in registry.active()} == {"A", "B"}


@pytest.mark.unit
def test_segment_only_session_is_hidden() -> None:
    # A stream that only ever hit segment endpoints (e.g. survived a
    # backend restart) has bytes but no identity — it must not surface
    # as a ghost "—" row.
    registry = NowPlayingRegistry()
    registry.note_segment("orphan", byte_count=5_000_000, segment_index=4)

    assert registry.active() == []
