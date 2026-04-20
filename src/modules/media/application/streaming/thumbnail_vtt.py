"""Pure helpers for the scrub-preview thumbnail sprite.

The player fetches a single WebVTT track alongside the video; each
cue in the VTT points at a rectangle of a sprite JPEG via the
``#xywh=x,y,w,h`` media-fragment syntax. This module owns the layout
math and the VTT text — both deterministic and easy to test. The
FFmpeg side (producing the sprite image itself) lives in
``HlsService`` so this module stays free of subprocess / filesystem
concerns.
"""

from dataclasses import dataclass

DEFAULT_INTERVAL_SECONDS = 10
DEFAULT_TILE_WIDTH = 160
DEFAULT_TILE_HEIGHT = 90
DEFAULT_COLUMNS = 10


@dataclass(frozen=True)
class SpriteLayout:
    """Geometry of a thumbnail sprite.

    Attributes:
        columns: Number of tiles per row in the sprite.
        rows: Number of rows actually needed to hold ``count`` tiles.
        tile_width: Width of each tile in pixels.
        tile_height: Height of each tile in pixels.
        count: Total number of tiles (frames) in the sprite.
    """

    columns: int
    rows: int
    tile_width: int
    tile_height: int
    count: int


def compute_layout(
    duration_seconds: float,
    *,
    interval: int = DEFAULT_INTERVAL_SECONDS,
    columns: int = DEFAULT_COLUMNS,
    tile_width: int = DEFAULT_TILE_WIDTH,
    tile_height: int = DEFAULT_TILE_HEIGHT,
) -> SpriteLayout:
    """Compute the sprite grid for a video of ``duration_seconds``.

    Takes the ceiling so a clip slightly shorter than ``interval``
    still gets one tile. Used by both the ffmpeg command builder and
    the VTT builder so the two stay in lock-step.
    """
    count = (
        1 if duration_seconds <= 0 else max(1, -(-int(duration_seconds) // interval))
    )
    rows = (count + columns - 1) // columns
    return SpriteLayout(
        columns=columns,
        rows=rows,
        tile_width=tile_width,
        tile_height=tile_height,
        count=count,
    )


def build_vtt(
    sprite_filename: str,
    layout: SpriteLayout,
    *,
    interval: int = DEFAULT_INTERVAL_SECONDS,
) -> str:
    """Render the WebVTT pointing each cue at a tile in the sprite.

    The returned text uses the ``<file>#xywh=x,y,w,h`` media-fragment
    syntax hls.js and video.js recognise natively — no plugin needed
    for basic scrub preview.
    """
    lines = ["WEBVTT", ""]
    for idx in range(layout.count):
        start = idx * interval
        end = start + interval
        col = idx % layout.columns
        row = idx // layout.columns
        x = col * layout.tile_width
        y = row * layout.tile_height
        lines.append(f"{_fmt_timestamp(start)} --> {_fmt_timestamp(end)}")
        lines.append(
            f"{sprite_filename}#xywh={x},{y},{layout.tile_width},{layout.tile_height}"
        )
        lines.append("")
    return "\n".join(lines)


def _fmt_timestamp(seconds: int) -> str:
    """Format an integer second count as the ``HH:MM:SS.000`` WebVTT timestamp."""
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.000"


__all__ = [
    "DEFAULT_COLUMNS",
    "DEFAULT_INTERVAL_SECONDS",
    "DEFAULT_TILE_HEIGHT",
    "DEFAULT_TILE_WIDTH",
    "SpriteLayout",
    "build_vtt",
    "compute_layout",
]
