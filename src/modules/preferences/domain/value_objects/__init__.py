"""Playback preferences value objects."""

from src.modules.preferences.domain.value_objects.credits_skip_mode import CreditsSkipMode
from src.modules.preferences.domain.value_objects.css_color import CssColor
from src.modules.preferences.domain.value_objects.intro_skip_mode import IntroSkipMode
from src.modules.preferences.domain.value_objects.preferences_id import PreferencesId
from src.modules.preferences.domain.value_objects.quality import Quality
from src.modules.preferences.domain.value_objects.speed import Speed
from src.modules.preferences.domain.value_objects.subtitle_appearance import (
    DEFAULT_SUBTITLE_BACKGROUND,
    DEFAULT_SUBTITLE_COLOR,
    DEFAULT_SUBTITLE_FONT_SIZE,
    DEFAULT_SUBTITLE_TEXT_EDGE,
    SubtitleAppearance,
)
from src.modules.preferences.domain.value_objects.subtitle_font_size import (
    SubtitleFontSize,
)
from src.modules.preferences.domain.value_objects.subtitle_text_edge import (
    SubtitleTextEdge,
)
from src.shared_kernel.value_objects.subtitle_mode import SubtitleMode

__all__ = [
    "DEFAULT_SUBTITLE_BACKGROUND",
    "DEFAULT_SUBTITLE_COLOR",
    "DEFAULT_SUBTITLE_FONT_SIZE",
    "DEFAULT_SUBTITLE_TEXT_EDGE",
    "CreditsSkipMode",
    "CssColor",
    "IntroSkipMode",
    "PreferencesId",
    "Quality",
    "Speed",
    "SubtitleAppearance",
    "SubtitleFontSize",
    "SubtitleMode",
    "SubtitleTextEdge",
]
