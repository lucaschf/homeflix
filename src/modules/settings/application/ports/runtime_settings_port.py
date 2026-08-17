"""Port for invalidating the runtime-settings cache."""

from typing import Protocol


class RuntimeSettingsInvalidatorPort(Protocol):
    """Drops the cached runtime-settings snapshot so the next read refreshes.

    Lets ``UpdateSettingUseCase`` depend only on the invalidation capability
    it needs, instead of importing the concrete ``RuntimeSettings``
    infrastructure class (ADR-004 — application depends on ports, not
    concretes). Satisfied structurally by ``RuntimeSettings`` at the
    composition root.
    """

    async def invalidate(self) -> None:
        """Discard the cached snapshot; the next read rebuilds it from the DB."""
        ...


__all__ = ["RuntimeSettingsInvalidatorPort"]
