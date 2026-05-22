"""Settings bounded context dependency container.

Provides the persistence wiring for the ``app_settings`` table
(ADR-013) and the :class:`RuntimeSettings` snapshot facade.

Phase 1 is foundation-only: no consumer reads the facade yet,
no use cases exist for admin writes, no routes are exposed.
The container is wired now so subsequent phases can plug in
without re-touching the composition root.
"""

from dependency_injector import containers, providers

from src.modules.settings.infrastructure.persistence.sqlalchemy_unit_of_work import (
    SqlAlchemySettingsUnitOfWorkFactory,
)
from src.modules.settings.infrastructure.runtime_settings import RuntimeSettings


class SettingsContainer(containers.DeclarativeContainer):  # type: ignore[misc]
    """Container for the Settings bounded context.

    Exposes:
        - The :class:`SettingsUnitOfWorkFactory` used by admin
          write paths (phase 2).
        - The :class:`RuntimeSettings` singleton — the typed,
          cached, DB-backed facade consumers will read once
          phase 2 migrates them off direct ``Settings`` access.
    """

    session_factory = providers.Dependency()

    settings_unit_of_work_factory = providers.Singleton(
        SqlAlchemySettingsUnitOfWorkFactory,
        session_factory=session_factory,
    )

    runtime_settings = providers.Singleton(
        RuntimeSettings,
        uow_factory=settings_unit_of_work_factory,
    )
