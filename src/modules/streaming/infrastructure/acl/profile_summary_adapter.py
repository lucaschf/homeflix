"""Adapter implementing ``ProfileSummaryPort`` via the identity UoW.

Resolves the display name for the profiles behind active playback
sessions. One small ``find_by_id`` per distinct profile — the session
count is tiny (a household), so a batch query isn't worth the extra
repo surface.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.modules.streaming.application.ports.profile_summary_port import (
    ProfileSummaryPort,
)
from src.shared_kernel.value_objects.profile_id import ProfileId

if TYPE_CHECKING:
    from collections.abc import Sequence

    from src.modules.identity.application.unit_of_work import (
        IdentityUnitOfWorkFactory,
    )


class ProfileSummaryAdapter(ProfileSummaryPort):
    """Reads profile names from the identity bounded context."""

    def __init__(self, identity_uow_factory: IdentityUnitOfWorkFactory) -> None:
        self._identity_uow_factory = identity_uow_factory

    async def names_for(self, profile_ids: Sequence[str]) -> dict[str, str]:
        """Resolve each distinct profile id to its display name."""
        unique = {pid for pid in profile_ids if pid}
        if not unique:
            return {}
        names: dict[str, str] = {}
        async with self._identity_uow_factory() as uow:
            for pid in unique:
                profile = await uow.profiles.find_by_id(ProfileId(pid))
                if profile is not None:
                    names[pid] = str(profile.name)
        return names


__all__ = ["ProfileSummaryAdapter"]
