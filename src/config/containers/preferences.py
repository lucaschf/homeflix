"""Preferences bounded context dependency container."""

from dependency_injector import containers, providers

from src.modules.preferences.application.use_cases.get_preferences import (
    GetPreferencesUseCase,
)
from src.modules.preferences.application.use_cases.update_preferences import (
    UpdatePreferencesUseCase,
)
from src.modules.preferences.infrastructure.persistence.repositories.preferences_repository import (
    PreferencesRepository,
)


class PreferencesContainer(containers.DeclarativeContainer):  # type: ignore[misc]
    """Container for Preferences bounded context."""

    session = providers.Dependency()

    preferences_repository = providers.Factory(
        PreferencesRepository,
        session=session,
    )

    get_preferences = providers.Factory(
        GetPreferencesUseCase,
        preferences_repository=preferences_repository,
    )

    update_preferences = providers.Factory(
        UpdatePreferencesUseCase,
        preferences_repository=preferences_repository,
    )
