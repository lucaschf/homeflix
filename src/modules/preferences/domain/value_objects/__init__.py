"""Playback preferences value objects."""

from src.modules.preferences.domain.value_objects.css_color import CssColor
from src.modules.preferences.domain.value_objects.preferences_id import PreferencesId
from src.modules.preferences.domain.value_objects.quality import Quality
from src.modules.preferences.domain.value_objects.speed import Speed
from src.modules.preferences.domain.value_objects.subtitle_appearance import (
    DEFAULT_SUBTITLE_BACKGROUND,
    DEFAULT_SUBTITLE_COLOR,
    DEFAULT_SUBTITLE_FONT_SIZE,
    SubtitleAppearance,
)
from src.modules.preferences.domain.value_objects.subtitle_font_size import (
    SubtitleFontSize,
)
from src.shared_kernel.value_objects.subtitle_mode import SubtitleMode

__all__ = [
    "DEFAULT_SUBTITLE_BACKGROUND",
    "DEFAULT_SUBTITLE_COLOR",
    "DEFAULT_SUBTITLE_FONT_SIZE",
    "CssColor",
    "PreferencesId",
    "Quality",
    "Speed",
    "SubtitleAppearance",
    "SubtitleFontSize",
    "SubtitleMode",
]
