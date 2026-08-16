"""Rule codes for the Playback Preferences bounded context."""


class PreferencesRuleCodes:
    """Message codes for preferences validation errors (used for i18n)."""

    SPEED_OUT_OF_RANGE = "PREFERENCES.SPEED.OUT_OF_RANGE"
    PREFERENCES_ID_INVALID = "PREFERENCES.ID.INVALID_FORMAT"
    SUBTITLE_COLOR_INVALID = "PREFERENCES.SUBTITLE_APPEARANCE.COLOR_INVALID"


__all__ = ["PreferencesRuleCodes"]
