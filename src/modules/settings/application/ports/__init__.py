"""Application ports for the settings bounded context."""

from src.modules.settings.application.ports.runtime_settings_port import (
    RuntimeSettingsInvalidatorPort,
)

__all__ = ["RuntimeSettingsInvalidatorPort"]
