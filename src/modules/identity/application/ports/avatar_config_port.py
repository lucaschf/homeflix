"""Protocol port for reading the avatar runtime-config bucket.

ADR-009-aligned (partial), the "Protocol port (no adapter)" variant:
Identity's avatar storage no longer names the Settings BC's concrete
``RuntimeSettings`` facade. This local Protocol describes only the getter
it calls; ``RuntimeSettings`` satisfies it structurally. The return type
is the Settings ``AvatarConfig`` VO (a stable published contract), not a
re-declared consumer DTO.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from src.modules.settings.domain.value_objects import AvatarConfig


class AvatarConfigPort(Protocol):
    """Access to the current avatar config."""

    async def avatar(self) -> AvatarConfig:
        """Return the current ``AvatarConfig``."""
        ...


__all__ = ["AvatarConfigPort"]
