"""ListSettingsUseCase — read every bucket for the admin panel."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.modules.settings.application.dtos import SettingDetail
from src.modules.settings.domain.value_objects import SettingKey
from src.modules.settings.infrastructure.runtime_settings import _DEFAULT_FACTORIES

if TYPE_CHECKING:
    from src.modules.settings.application.unit_of_work import (
        SettingsUnitOfWorkFactory,
    )
    from src.modules.settings.domain.entities import Setting


_SYNTHETIC_DEFAULT_SOURCE = "default"


class ListSettingsUseCase:
    """Return one :class:`SettingDetail` per :class:`SettingKey`.

    Buckets without a persisted row are synthesised from the Pydantic
    VO default with ``source='default'`` and ``updated_at=None`` so the
    admin panel can show "factory" alongside operator-edited rows in
    the same list without a second round-trip.

    The use case bypasses the :class:`RuntimeSettings` TTL cache and
    reads straight from the DB — admins editing the form must see the
    *durable* state, not whatever the snapshot last picked up.
    """

    def __init__(self, uow_factory: SettingsUnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def execute(self) -> list[SettingDetail]:
        """List every bucket (persisted or defaulted) in :class:`SettingKey` order."""
        async with self._uow_factory() as uow:
            persisted = {row.id: row for row in await uow.settings.list_all()}

        return [
            _to_detail(persisted[key]) if key in persisted else _default_detail(key)
            for key in SettingKey
        ]


def _to_detail(setting: Setting) -> SettingDetail:
    return SettingDetail(
        key=setting.id.value,
        value=setting.value.model_dump(mode="json"),
        source=setting.source.value,
        updated_by_user_id=setting.updated_by_user_id,
        updated_at=setting.updated_at.isoformat() if setting.updated_at else None,
    )


def _default_detail(key: SettingKey) -> SettingDetail:
    vo_type = _DEFAULT_FACTORIES[key]
    return SettingDetail(
        key=key.value,
        value=vo_type().model_dump(mode="json"),
        source=_SYNTHETIC_DEFAULT_SOURCE,
        updated_by_user_id=None,
        updated_at=None,
    )


__all__ = ["ListSettingsUseCase"]
