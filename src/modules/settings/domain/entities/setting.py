"""Setting aggregate — one row per configuration bucket."""

from __future__ import annotations

from typing import ClassVar, Self

from pydantic import model_validator

from src.building_blocks.domain.entity import AggregateRoot
from src.modules.settings.domain.value_objects import (
    AvatarConfig,
    ConfigVO,
    IntroDetectionConfig,
    ScanDedupConfig,
    SchedulerConfig,
    SettingKey,
    SettingSource,
    StreamingConfig,
    ThumbnailBackfillConfig,
)


class Setting(AggregateRoot[SettingKey]):
    """Persisted snapshot of a configuration bucket.

    The aggregate's identity is the :class:`SettingKey` enum value —
    the same string used as the primary key in ``app_settings`` and as
    the URL slug under ``/admin/settings/<key>``. The ``value`` field
    carries the configuration VO whose type is dictated by ``id``; the
    aggregate validates this invariant on construction so the
    persistence layer can trust the in-memory shape without re-checking.

    Attributes:
        id: Which configuration bucket this row carries.
        value: The current configuration. Its concrete type must
            match the type expected for ``id`` (see
            :attr:`_KEY_TO_VO_TYPE`).
        source: Provenance of the value — migration seed, admin edit,
            or manual SQL override.
        updated_by_user_id: Identifier of the user that last wrote
            this setting via the admin panel. ``None`` for
            migration-seeded rows; may be ``None`` for ``SQL_OVERRIDE``
            rows if the operator did not fill it in.

    Example:
        >>> setting = Setting(
        ...     id=SettingKey.INTRO_DETECTION,
        ...     value=IntroDetectionConfig(enabled=True),
        ...     source=SettingSource.ADMIN,
        ...     updated_by_user_id="usr_abc123",
        ... )
        >>> updated = setting.with_updates(
        ...     value=setting.value.with_updates(min_confidence=0.85),
        ... )
    """

    id: SettingKey
    value: ConfigVO
    source: SettingSource
    updated_by_user_id: str | None = None

    _KEY_TO_VO_TYPE: ClassVar[dict[SettingKey, type]] = {
        SettingKey.SCHEDULER: SchedulerConfig,
        SettingKey.THUMBNAIL_BACKFILL: ThumbnailBackfillConfig,
        SettingKey.INTRO_DETECTION: IntroDetectionConfig,
        SettingKey.STREAMING: StreamingConfig,
        SettingKey.AVATAR: AvatarConfig,
        SettingKey.SCAN_DEDUP: ScanDedupConfig,
    }

    @model_validator(mode="after")
    def _validate_value_matches_key(self) -> Self:
        expected = self._KEY_TO_VO_TYPE[self.id]
        if not isinstance(self.value, expected):
            raise ValueError(
                f"Setting with key {self.id.value!r} requires value of type "
                f"{expected.__name__}, got {type(self.value).__name__}",
            )
        return self


__all__ = ["Setting"]
