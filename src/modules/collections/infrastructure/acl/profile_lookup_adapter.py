"""Adapter implementing ``ProfileLookupPort`` via the identity UoW.

Resolves owner display names for followed-list rows and shared-list
previews. One of only two files in the Collections BC that import from
the Identity BC; above it the use cases see only the abstract port
(ADR-009).
"""

from collections.abc import Sequence

from src.modules.collections.application.ports.profile_lookup_port import (
    ProfileLookupPort,
)
from src.modules.identity.application.unit_of_work import IdentityUnitOfWorkFactory
from src.shared_kernel.value_objects.profile_id import ProfileId


class ProfileLookupAdapter(ProfileLookupPort):
    """Resolve profile display names via the Identity Unit of Work."""

    def __init__(self, identity_uow_factory: IdentityUnitOfWorkFactory) -> None:
        self._identity_uow_factory = identity_uow_factory

    async def get_names(self, profile_ids: Sequence[str]) -> dict[str, str]:
        """Resolve display names, skipping ids that don't resolve.

        The identity repository has no batch id lookup, so this issues
        one ``find_by_id`` per *unique* id inside a single UoW. The
        caller set (followed-list owners) is small, so the loop stays
        cheap.
        """
        unique_ids = list(dict.fromkeys(profile_ids))
        if not unique_ids:
            return {}
        names: dict[str, str] = {}
        async with self._identity_uow_factory() as uow:
            for pid in unique_ids:
                profile = await uow.profiles.find_by_id(ProfileId(pid))
                if profile is not None:
                    names[pid] = profile.name.value
        return names


__all__ = ["ProfileLookupAdapter"]
