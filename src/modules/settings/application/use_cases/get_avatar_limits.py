"""GetAvatarLimitsUseCase — the avatar upload limits a member's client needs."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.modules.settings.application.dtos import AvatarLimits

if TYPE_CHECKING:
    from src.modules.settings.application.ports import AvatarConfigReaderPort


class GetAvatarLimitsUseCase:
    """Project the avatar config down to what a client may know.

    Reads the same cached snapshot the storage adapter enforces on upload
    (:class:`RuntimeSettings`), **not** the durable row
    :class:`ListSettingsUseCase` reads for the admin panel. The two can
    disagree for up to the snapshot TTL after an operator edit, and a
    client told a cap the upload route would not honour is worse than one
    told a slightly stale cap: reading the enforcing source makes the
    advertised limit the enforced limit by construction.
    """

    def __init__(self, avatar_config: AvatarConfigReaderPort) -> None:
        self._avatar_config = avatar_config

    async def execute(self) -> AvatarLimits:
        """Return the limits in force for an avatar upload right now."""
        config = await self._avatar_config.avatar()
        return AvatarLimits(
            max_size_bytes=config.max_size_bytes,
            max_size_mb=config.max_size_mb,
            size_pixels=config.size_pixels,
        )


__all__ = ["GetAvatarLimitsUseCase"]
