"""Tests for the thumbnail VTT / sprite layout helpers."""

import pytest

from src.modules.media.application.streaming.thumbnail_vtt import (
    DEFAULT_COLUMNS,
    DEFAULT_INTERVAL_SECONDS,
    DEFAULT_TILE_HEIGHT,
    DEFAULT_TILE_WIDTH,
    build_vtt,
    compute_layout,
)


@pytest.mark.unit
class TestComputeLayout:
    """Layout math for the sprite grid."""

    def test_should_produce_single_tile_for_short_clip(self) -> None:
        # A 3-second clip still gets one tile so the player has something
        # to hover on — taking the ceiling is what makes that work.
        layout = compute_layout(3.0)

        assert layout.count == 1
        assert layout.rows == 1
        assert layout.columns == DEFAULT_COLUMNS
        assert layout.tile_width == DEFAULT_TILE_WIDTH
        assert layout.tile_height == DEFAULT_TILE_HEIGHT

    def test_should_ceil_when_duration_is_not_a_multiple_of_interval(self) -> None:
        # 25 seconds at the default 10s interval covers cues at 0s, 10s,
        # and 20s — three tiles, not two.
        layout = compute_layout(25.0)
        assert layout.count == 3

    def test_should_ceil_fractional_durations_past_an_interval_boundary(self) -> None:
        # Regression: integer truncation of ``duration_seconds`` before
        # the ceiling would treat 10.1s as exactly 10s and emit a single
        # tile, losing the last ~100ms of the clip. The ceiling must
        # operate on the raw float.
        layout = compute_layout(10.1)
        assert layout.count == 2

    def test_should_wrap_to_new_row_after_full_column_run(self) -> None:
        # 11 intervals at 10 columns = 2 rows (10 + 1).
        layout = compute_layout(110.0)
        assert layout.count == 11
        assert layout.rows == 2

    def test_should_return_one_tile_for_zero_or_negative_duration(self) -> None:
        assert compute_layout(0.0).count == 1
        assert compute_layout(-5.0).count == 1

    def test_should_honor_custom_interval_and_columns(self) -> None:
        layout = compute_layout(
            duration_seconds=120.0,
            interval=30,
            columns=2,
        )
        # 120 / 30 = 4 tiles → 2 rows of 2 columns.
        assert layout.count == 4
        assert layout.columns == 2
        assert layout.rows == 2


@pytest.mark.unit
class TestBuildVtt:
    """WebVTT text generation for a given sprite layout."""

    def test_should_emit_webvtt_header(self) -> None:
        layout = compute_layout(10.0)
        vtt = build_vtt("sprite.jpg", layout)

        assert vtt.startswith("WEBVTT\n")

    def test_should_emit_one_cue_per_tile_with_timestamps(self) -> None:
        layout = compute_layout(25.0)  # 3 tiles at 10s interval
        vtt = build_vtt("sprite.jpg", layout)

        # Concrete ranges prove the math; the count + last-cue
        # assertions tie the VTT output tightly to ``layout`` so a
        # future change to either side can't silently drift.
        assert "00:00:00.000 --> 00:00:10.000" in vtt
        assert "00:00:10.000 --> 00:00:20.000" in vtt
        assert "00:00:20.000 --> 00:00:30.000" in vtt

        assert vtt.count("-->") == layout.count
        cue_lines = [line for line in vtt.splitlines() if "-->" in line]
        assert cue_lines[-1].endswith("00:00:30.000")

    def test_should_reference_sprite_with_xywh_fragment(self) -> None:
        layout = compute_layout(10.0)
        vtt = build_vtt("sprite.jpg", layout)

        assert f"sprite.jpg#xywh=0,0,{DEFAULT_TILE_WIDTH},{DEFAULT_TILE_HEIGHT}" in vtt

    def test_should_advance_x_across_columns_then_wrap_to_next_row(self) -> None:
        # 11 tiles with 10 columns: tile 0..9 share y=0, tile 10 jumps to y=90.
        layout = compute_layout(duration_seconds=110.0)
        vtt = build_vtt("sprite.jpg", layout)

        expected_tile_9 = (
            f"sprite.jpg#xywh={9 * DEFAULT_TILE_WIDTH},0,"
            f"{DEFAULT_TILE_WIDTH},{DEFAULT_TILE_HEIGHT}"
        )
        expected_tile_10 = (
            f"sprite.jpg#xywh=0,{DEFAULT_TILE_HEIGHT},"
            f"{DEFAULT_TILE_WIDTH},{DEFAULT_TILE_HEIGHT}"
        )
        assert expected_tile_9 in vtt
        assert expected_tile_10 in vtt

    def test_should_format_timestamps_past_one_hour(self) -> None:
        # 3700 seconds → ~61m => tile 370 at the 3700s cue.
        layout = compute_layout(3700.0, interval=DEFAULT_INTERVAL_SECONDS)
        vtt = build_vtt("sprite.jpg", layout)

        assert "01:01:30.000 --> 01:01:40.000" in vtt

    def test_should_preserve_sprite_filename_verbatim(self) -> None:
        layout = compute_layout(10.0)
        vtt = build_vtt("custom_name.jpg", layout)

        assert "custom_name.jpg#xywh=" in vtt
        assert "sprite.jpg" not in vtt
