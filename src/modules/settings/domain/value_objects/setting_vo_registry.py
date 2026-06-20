"""Single source of truth for the ``SettingKey`` → configuration VO map.

The same mapping used to be copied in the ``Setting`` aggregate, the
``SettingMapper`` and the ``RuntimeSettings`` facade — adding a bucket
meant editing four places, and forgetting one broke a different
subsystem (validation, persistence or runtime defaults). Every layer
now reads this registry; adding a bucket is the enum member, the VO,
and **one** entry here (covered by a completeness test).
"""

from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

from src.building_blocks.domain.value_objects import CompoundValueObject
from src.modules.settings.domain.value_objects.avatar_config import AvatarConfig
from src.modules.settings.domain.value_objects.credits_detection_config import (
    CreditsDetectionConfig,
)
from src.modules.settings.domain.value_objects.intro_detection_config import (
    IntroDetectionConfig,
)
from src.modules.settings.domain.value_objects.scan_dedup_config import ScanDedupConfig
from src.modules.settings.domain.value_objects.scheduler_config import SchedulerConfig
from src.modules.settings.domain.value_objects.setting_key import SettingKey
from src.modules.settings.domain.value_objects.streaming_config import StreamingConfig
from src.modules.settings.domain.value_objects.thumbnail_backfill_config import (
    ThumbnailBackfillConfig,
)

SETTING_VO_TYPES: Final[Mapping[SettingKey, type[CompoundValueObject]]] = MappingProxyType(
    {
        SettingKey.SCHEDULER: SchedulerConfig,
        SettingKey.THUMBNAIL_BACKFILL: ThumbnailBackfillConfig,
        SettingKey.INTRO_DETECTION: IntroDetectionConfig,
        SettingKey.CREDITS_DETECTION: CreditsDetectionConfig,
        SettingKey.STREAMING: StreamingConfig,
        SettingKey.AVATAR: AvatarConfig,
        SettingKey.SCAN_DEDUP: ScanDedupConfig,
    }
)
"""Read-only map from setting bucket to the VO type its row carries."""


def vo_type_for(key: SettingKey) -> type[CompoundValueObject]:
    """Return the configuration VO type persisted under ``key``.

    Args:
        key: The setting bucket identifier.

    Returns:
        The concrete ``CompoundValueObject`` subclass for the bucket.
    """
    return SETTING_VO_TYPES[key]


__all__ = ["SETTING_VO_TYPES", "vo_type_for"]
