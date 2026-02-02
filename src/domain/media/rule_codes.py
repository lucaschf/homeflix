"""Business rule codes for the media domain.

Centralizes rule_code constants used in BusinessRuleViolationException
to avoid typos and facilitate maintenance.
"""


class MediaRuleCodes:
    """Rule codes for media domain business rule violations."""

    EPISODE_SERIES_MISMATCH = "EPISODE_SERIES_MISMATCH"
    EPISODE_SEASON_MISMATCH = "EPISODE_SEASON_MISMATCH"
    SEASON_SERIES_MISMATCH = "SEASON_SERIES_MISMATCH"


__all__ = ["MediaRuleCodes"]
