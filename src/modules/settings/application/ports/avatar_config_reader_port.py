"""Port for reading the avatar config bucket from the application layer.

The settings use cases must not name :class:`RuntimeSettings`, which is
this BC's own infrastructure (ADR-004 — application depends on ports, not
concretes). This Protocol describes only the getter
:class:`GetAvatarLimitsUseCase` calls; ``RuntimeSettings`` satisfies it
structurally at the composition root.

The return type is the :class:`AvatarConfig` VO — settings' own domain,
so no consumer DTO is needed here (unlike identity's
``AvatarConfigPort``, which crosses a BC boundary to reach the same VO).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from src.modules.settings.domain.value_objects import AvatarConfig


class AvatarConfigReaderPort(Protocol):
    """Read access to the avatar config currently in force."""

    async def avatar(self) -> AvatarConfig:
        """Return the current :class:`AvatarConfig`."""
        ...


__all__ = ["AvatarConfigReaderPort"]
