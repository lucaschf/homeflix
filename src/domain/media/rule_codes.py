"""Business rule codes for the media domain.

Centralizes rule_code constants used in BusinessRuleViolationException
to avoid typos and facilitate maintenance.
"""

from enum import StrEnum


class MediaRuleCodes(StrEnum):
    """Rule codes for media domain business rule violations."""

    EPISODE_SERIES_MISMATCH = "EPISODE_SERIES_MISMATCH"
    EPISODE_SEASON_MISMATCH = "EPISODE_SEASON_MISMATCH"
    SEASON_SERIES_MISMATCH = "SEASON_SERIES_MISMATCH"
    INVALID_MEDIA_ID_FORMAT = "INVALID_MEDIA_ID_FORMAT"
    UNKNOWN_MEDIA_PREFIX = "UNKNOWN_MEDIA_PREFIX"


__all__ = ["MediaRuleCodes"]
