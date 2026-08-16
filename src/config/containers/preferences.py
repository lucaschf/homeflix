"""Preferences bounded context dependency container."""

from typing import Any

from dependency_injector import containers, providers

from src.modules.preferences.application.use_cases.get_preferences import (
    GetPreferencesUseCase,
)
from src.modules.preferences.application.use_cases.update_preferences import (
    UpdatePreferencesUseCase,
)
from src.modules.preferences.infrastructure.persistence.sqlalchemy_unit_of_work import (
    SqlAlchemyPreferencesUnitOfWorkFactory,
)


class PreferencesContainer(containers.DeclarativeContainer):
    """Container for Preferences bounded context."""

    session_factory = providers.Dependency[Any]()

    preferences_unit_of_work_factory = providers.Singleton(
        SqlAlchemyPreferencesUnitOfWorkFactory,
        session_factory=session_factory,
    )

    get_preferences = providers.Factory(
        GetPreferencesUseCase,
        uow_factory=preferences_unit_of_work_factory,
    )

    update_preferences = providers.Factory(
        UpdatePreferencesUseCase,
        uow_factory=preferences_unit_of_work_factory,
    )
