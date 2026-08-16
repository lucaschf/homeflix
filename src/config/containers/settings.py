"""Settings bounded context dependency container.

Provides the persistence wiring for the ``app_settings`` table
(ADR-013), the :class:`RuntimeSettings` snapshot facade, and the
admin-panel use cases (phase 4).
"""

from typing import Any

from dependency_injector import containers, providers

from src.modules.settings.application.use_cases import (
    ListSettingsUseCase,
    UpdateSettingUseCase,
)
from src.modules.settings.infrastructure.persistence.sqlalchemy_unit_of_work import (
    SqlAlchemySettingsUnitOfWorkFactory,
)
from src.modules.settings.infrastructure.runtime_settings import RuntimeSettings


class SettingsContainer(containers.DeclarativeContainer):
    """Container for the Settings bounded context.

    Exposes:
        - The :class:`SettingsUnitOfWorkFactory` used by admin
          write paths.
        - The :class:`RuntimeSettings` singleton — typed, cached,
          DB-backed facade consumed by HLS / scheduler / avatar.
        - Admin use cases that back ``GET`` and ``PATCH`` on
          ``/api/v1/admin/settings`` (phase 4).
    """

    session_factory = providers.Dependency[Any]()

    settings_unit_of_work_factory = providers.Singleton(
        SqlAlchemySettingsUnitOfWorkFactory,
        session_factory=session_factory,
    )

    runtime_settings = providers.Singleton(
        RuntimeSettings,
        uow_factory=settings_unit_of_work_factory,
    )

    list_settings = providers.Factory(
        ListSettingsUseCase,
        uow_factory=settings_unit_of_work_factory,
    )

    update_setting = providers.Factory(
        UpdateSettingUseCase,
        uow_factory=settings_unit_of_work_factory,
        runtime_settings=runtime_settings,
    )
