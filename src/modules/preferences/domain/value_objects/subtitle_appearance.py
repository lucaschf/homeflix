"""SubtitleAppearance value object — how subtitles look in the player."""

from src.building_blocks.domain import CompoundValueObject
from src.modules.preferences.domain.value_objects.css_color import CssColor
from src.modules.preferences.domain.value_objects.subtitle_font_size import (
    SubtitleFontSize,
)
from src.modules.preferences.domain.value_objects.subtitle_text_edge import (
    SubtitleTextEdge,
)

DEFAULT_SUBTITLE_COLOR = "#FFFFFF"
DEFAULT_SUBTITLE_BACKGROUND = "rgba(0, 0, 0, 0.75)"
DEFAULT_SUBTITLE_FONT_SIZE = SubtitleFontSize.MEDIUM
DEFAULT_SUBTITLE_TEXT_EDGE = SubtitleTextEdge.DROP_SHADOW


class SubtitleAppearance(CompoundValueObject):
    """Per-profile styling for the subtitle overlay in the player.

    Bundles the knobs the player's custom subtitle overlay reads — text
    color, background color, relative size, and text-edge style — into one
    value so they travel and validate together. Account-level styling that
    syncs across devices, mirroring how Netflix/YouTube persist caption style.

    Attributes:
        color: Subtitle text color (validated CSS color).
        background: Subtitle background color, typically semi-transparent
            (validated CSS color).
        font_size: Relative size tier the player scales to the viewport.
        text_edge: How the glyphs are outlined for legibility (none / drop
            shadow / hard outline).

    Example:
        >>> a = SubtitleAppearance.default()
        >>> a.color.value
        '#FFFFFF'
        >>> a.font_size
        <SubtitleFontSize.MEDIUM: 'medium'>
    """

    color: CssColor
    background: CssColor
    font_size: SubtitleFontSize
    text_edge: SubtitleTextEdge

    @classmethod
    def default(cls) -> "SubtitleAppearance":
        """The white-on-dim default applied until a profile customizes it."""
        return cls(
            color=CssColor(DEFAULT_SUBTITLE_COLOR),
            background=CssColor(DEFAULT_SUBTITLE_BACKGROUND),
            font_size=DEFAULT_SUBTITLE_FONT_SIZE,
            text_edge=DEFAULT_SUBTITLE_TEXT_EDGE,
        )


__all__ = [
    "DEFAULT_SUBTITLE_BACKGROUND",
    "DEFAULT_SUBTITLE_COLOR",
    "DEFAULT_SUBTITLE_FONT_SIZE",
    "DEFAULT_SUBTITLE_TEXT_EDGE",
    "SubtitleAppearance",
]
