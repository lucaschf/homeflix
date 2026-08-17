"""UpdateSettingUseCase — admin-panel write for a single bucket."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.modules.settings.application.dtos import SettingDetail, UpdateSettingInput
from src.modules.settings.domain.entities import Setting
from src.modules.settings.domain.value_objects import (
    SettingKey,
    SettingSource,
    vo_type_for,
)

if TYPE_CHECKING:
    from src.modules.settings.application.ports import RuntimeSettingsInvalidatorPort
    from src.modules.settings.application.unit_of_work import (
        SettingsUnitOfWorkFactory,
    )


class UpdateSettingUseCase:
    """Replace the persisted VO for a bucket and invalidate the cache.

    Full-replace semantics: ``input.value`` carries the entire VO
    payload — the UI submits the whole form, the use case
    re-validates it through the matching VO type, upserts the row with
    ``source='admin'`` and the operator's user id, then invalidates
    the :class:`RuntimeSettings` snapshot so consumers pick up the new
    state on their next read instead of waiting out the TTL.

    Pydantic validation failure (out-of-range field, cross-field
    invariant, unknown attribute) raises a
    :class:`DomainValidationException` before any write — FastAPI
    surfaces it as ``400 DOMAIN_VALIDATION_ERROR`` via the standard
    exception handlers.

    Raises:
        ValueError: When ``input.key`` is not a known
            :class:`SettingKey`. Routes only ever pass enum-derived
            slugs, so in practice this is defensive against
            non-HTTP callers.
    """

    def __init__(
        self,
        uow_factory: SettingsUnitOfWorkFactory,
        runtime_settings: RuntimeSettingsInvalidatorPort,
    ) -> None:
        self._uow_factory = uow_factory
        self._runtime_settings = runtime_settings

    async def execute(self, input_dto: UpdateSettingInput) -> SettingDetail:
        """Validate, upsert, invalidate cache, return the refreshed detail."""
        key = SettingKey(input_dto.key)
        vo_type = vo_type_for(key)
        value_vo = vo_type.model_validate(input_dto.value)

        setting = Setting(
            id=key,
            value=value_vo,
            source=SettingSource.ADMIN,
            updated_by_user_id=input_dto.acting_admin_id,
        )

        async with self._uow_factory() as uow:
            persisted = await uow.settings.upsert(setting)

        await self._runtime_settings.invalidate()

        return SettingDetail(
            key=persisted.id.value,
            value=persisted.value.model_dump(mode="json"),
            source=persisted.source.value,
            updated_by_user_id=(
                persisted.updated_by_user_id.value if persisted.updated_by_user_id else None
            ),
            updated_at=persisted.updated_at.isoformat() if persisted.updated_at else None,
        )


__all__ = ["UpdateSettingUseCase"]
