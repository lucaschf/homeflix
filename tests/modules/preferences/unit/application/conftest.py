"""Unit-test helpers for the preferences bounded context."""

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

from src.modules.preferences.application.unit_of_work import (
    PreferencesUnitOfWork,
    PreferencesUnitOfWorkFactory,
)
from src.modules.preferences.domain.repositories import PreferencesRepository


@dataclass
class PreferencesUoWMocks:
    """Bundle of mocks produced by ``make_preferences_uow_mock``.

    Attributes:
        factory: Callable matching ``PreferencesUnitOfWorkFactory``.
        uow: The mock ``PreferencesUnitOfWork`` — an async context
            manager returning itself.
        preferences: Mock ``PreferencesRepository`` exposed as
            ``uow.preferences``.
    """

    factory: PreferencesUnitOfWorkFactory
    uow: PreferencesUnitOfWork
    preferences: AsyncMock


def make_preferences_uow_mock() -> PreferencesUoWMocks:
    """Build a mock :class:`PreferencesUnitOfWork` factory."""
    preferences = AsyncMock(spec=PreferencesRepository)
    uow: PreferencesUnitOfWork = AsyncMock()
    uow.__aenter__.return_value = uow  # type: ignore[attr-defined]
    uow.__aexit__.return_value = None  # type: ignore[attr-defined]
    uow.preferences = preferences
    factory = MagicMock(return_value=uow)
    return PreferencesUoWMocks(factory=factory, uow=uow, preferences=preferences)
