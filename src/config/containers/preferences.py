"""Preferences bounded context dependency container."""

from dependency_injector import containers, providers

from src.modules.preferences.application.use_cases.get_preferences import (
    GetPreferencesUseCase,
)
from src.modules.preferences.application.use_cases.update_preferences import (
    UpdatePreferencesUseCase,
)
from src.modules.preferences.infrastructure.persistence.repositories import (
    SQLAlchemyPreferencesRepository,
)
from src.modules.preferences.infrastructure.persistence.sqlalchemy_unit_of_work import (
    SqlAlchemyPreferencesUnitOfWorkFactory,
)


class PreferencesContainer(containers.DeclarativeContainer):  # type: ignore[misc]
    """Container for Preferences bounded context."""

    session = providers.Dependency()
    session_factory = providers.Dependency()

    preferences_repository = providers.Factory(
        SQLAlchemyPreferencesRepository,
        session=session,
    )

    preferences_unit_of_work_factory = providers.Singleton(
        SqlAlchemyPreferencesUnitOfWorkFactory,
        session_factory=session_factory,
    )

    get_preferences = providers.Factory(
        GetPreferencesUseCase,
        preferences_repository=preferences_repository,
    )

    update_preferences = providers.Factory(
        UpdatePreferencesUseCase,
        uow_factory=preferences_unit_of_work_factory,
    )
