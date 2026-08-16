"""Subtitle text-edge enumeration."""

from enum import StrEnum


class SubtitleTextEdge(StrEnum):
    """How the subtitle text is outlined for legibility over the picture.

    The player maps each tier to a concrete CSS treatment: ``NONE`` draws the
    glyphs flat, ``DROP_SHADOW`` (the default, matching the pre-existing look)
    adds a soft shadow, and ``OUTLINE`` traces a hard contour that stays
    readable over bright frames. String values are the canonical ones
    persisted on the ``preferences`` table.
    """

    NONE = "none"
    DROP_SHADOW = "shadow"
    OUTLINE = "outline"


__all__ = ["SubtitleTextEdge"]
