"""Value objects for the settings BC.

Each ``*Config`` VO groups a coherent bucket of operational tunables
(see ADR-013). The :class:`SettingKey` enum identifies which VO a
persisted row in ``app_settings`` carries; :class:`SettingSource` marks
the row's provenance for audit.
"""

from src.modules.settings.domain.value_objects.avatar_config import AvatarConfig
from src.modules.settings.domain.value_objects.intro_detection_config import (
    IntroDetectionConfig,
)
from src.modules.settings.domain.value_objects.scan_dedup_config import ScanDedupConfig
from src.modules.settings.domain.value_objects.scheduler_config import SchedulerConfig
from src.modules.settings.domain.value_objects.setting_key import SettingKey
from src.modules.settings.domain.value_objects.setting_source import SettingSource
from src.modules.settings.domain.value_objects.setting_vo_registry import (
    SETTING_VO_TYPES,
    vo_type_for,
)
from src.modules.settings.domain.value_objects.streaming_config import StreamingConfig
from src.modules.settings.domain.value_objects.thumbnail_backfill_config import (
    ThumbnailBackfillConfig,
)

ConfigVO = (
    SchedulerConfig
    | ThumbnailBackfillConfig
    | IntroDetectionConfig
    | StreamingConfig
    | AvatarConfig
    | ScanDedupConfig
)
"""Union of all configuration VOs persisted in ``app_settings``."""

__all__ = [
    "AvatarConfig",
    "ConfigVO",
    "SETTING_VO_TYPES",
    "IntroDetectionConfig",
    "ScanDedupConfig",
    "SchedulerConfig",
    "SettingKey",
    "SettingSource",
    "StreamingConfig",
    "ThumbnailBackfillConfig",
    "vo_type_for",
]
