"""Runtime-settings facade — typed access to DB-backed config VOs.

Phase 1 (ADR-013): consumers don't read this yet — the facade is
introduced standalone so the persistence wiring and snapshot/TTL
behavior can be exercised in isolation. Phase 2 wires consumers
(scheduler, intro detection, HLS, thumbnail backfill, avatar)
through the typed getters below, replacing direct ``Settings``
field access.

Semantics:

- Resolution order is ``DB > Pydantic default`` (no env layer for
  migrated fields).
- A short TTL cache is rebuilt with one ``list_all()`` per refresh.
- :meth:`invalidate` lets admin-panel write endpoints force the
  next read to re-fetch, so an edit propagates within microseconds
  rather than waiting for the TTL.
- The Pydantic VO defaults are used both as the baseline (when no
  row exists) and as the validation contract (a row whose JSON
  fails VO validation raises during ``refresh`` before any consumer
  sees a partial snapshot).
"""

from __future__ import annotations

import time
from asyncio import Lock
from typing import TYPE_CHECKING, cast

from src.modules.settings.domain.value_objects import (
    AvatarConfig,
    ConfigVO,
    IntroDetectionConfig,
    SchedulerConfig,
    SettingKey,
    StreamingConfig,
    ThumbnailBackfillConfig,
)

if TYPE_CHECKING:
    from src.modules.settings.application.unit_of_work import (
        SettingsUnitOfWorkFactory,
    )
    from src.modules.settings.domain.entities import Setting

_DEFAULT_FACTORIES: dict[SettingKey, type[ConfigVO]] = {
    SettingKey.SCHEDULER: SchedulerConfig,
    SettingKey.THUMBNAIL_BACKFILL: ThumbnailBackfillConfig,
    SettingKey.INTRO_DETECTION: IntroDetectionConfig,
    SettingKey.STREAMING: StreamingConfig,
    SettingKey.AVATAR: AvatarConfig,
}


class RuntimeSettings:
    """Typed, cached, DB-backed access to operational tunables.

    Construct once at startup (singleton scope in the DI container)
    and hand the same instance to every consumer.

    Args:
        uow_factory: A :class:`SettingsUnitOfWorkFactory` used to
            open a short-lived read session per refresh. The facade
            never holds a session between refreshes.
        cache_ttl_seconds: How long a snapshot is considered fresh.
            Lower = faster admin-panel propagation; higher = fewer
            DB round-trips on the hot path. Default 30s matches
            ADR-013.

    Example:
        >>> rs = RuntimeSettings(uow_factory)
        >>> cfg = await rs.scheduler()
        >>> if cfg.enabled:
        ...     ...
    """

    def __init__(
        self,
        uow_factory: SettingsUnitOfWorkFactory,
        cache_ttl_seconds: int = 30,
    ) -> None:
        self._uow_factory = uow_factory
        self._ttl = cache_ttl_seconds
        self._snapshot: dict[SettingKey, ConfigVO] = {
            key: vo_type() for key, vo_type in _DEFAULT_FACTORIES.items()
        }
        self._snapshot_loaded_at: float = 0.0
        self._lock = Lock()

    async def refresh(self) -> None:
        """Reload the snapshot from the DB.

        Any row that fails VO validation raises; the previous
        snapshot is retained so consumers never observe a partial
        state.
        """
        async with self._uow_factory() as uow:
            rows: list[Setting] = list(await uow.settings.list_all())
        new_snapshot: dict[SettingKey, ConfigVO] = {
            key: vo_type() for key, vo_type in _DEFAULT_FACTORIES.items()
        }
        for row in rows:
            new_snapshot[row.id] = row.value
        self._snapshot = new_snapshot
        self._snapshot_loaded_at = time.monotonic()

    async def invalidate(self) -> None:
        """Force the next read to refresh from the DB."""
        async with self._lock:
            self._snapshot_loaded_at = 0.0

    async def _ensure_fresh(self) -> None:
        if time.monotonic() - self._snapshot_loaded_at <= self._ttl:
            return
        async with self._lock:
            if time.monotonic() - self._snapshot_loaded_at > self._ttl:
                await self.refresh()

    async def scheduler(self) -> SchedulerConfig:
        """Return the current :class:`SchedulerConfig` snapshot."""
        await self._ensure_fresh()
        return cast(SchedulerConfig, self._snapshot[SettingKey.SCHEDULER])

    async def thumbnail_backfill(self) -> ThumbnailBackfillConfig:
        """Return the current :class:`ThumbnailBackfillConfig` snapshot."""
        await self._ensure_fresh()
        return cast(
            ThumbnailBackfillConfig,
            self._snapshot[SettingKey.THUMBNAIL_BACKFILL],
        )

    async def intro_detection(self) -> IntroDetectionConfig:
        """Return the current :class:`IntroDetectionConfig` snapshot."""
        await self._ensure_fresh()
        return cast(
            IntroDetectionConfig,
            self._snapshot[SettingKey.INTRO_DETECTION],
        )

    async def streaming(self) -> StreamingConfig:
        """Return the current :class:`StreamingConfig` snapshot."""
        await self._ensure_fresh()
        return cast(StreamingConfig, self._snapshot[SettingKey.STREAMING])

    async def avatar(self) -> AvatarConfig:
        """Return the current :class:`AvatarConfig` snapshot."""
        await self._ensure_fresh()
        return cast(AvatarConfig, self._snapshot[SettingKey.AVATAR])


__all__ = ["RuntimeSettings"]
