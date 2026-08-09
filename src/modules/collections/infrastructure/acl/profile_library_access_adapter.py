"""Adapter implementing ``ProfileLibraryAccessPort`` via the identity UoW.

One of only two files in the Collections BC that import from the
Identity BC (the other resolves display names). Above the adapter, the
use cases see only the abstract port — the cross-BC boundary stays
explicit, per ADR-009.
"""

from src.modules.collections.application.ports.profile_library_access_port import (
    ProfileLibraryAccessPort,
)
from src.modules.identity.application.unit_of_work import IdentityUnitOfWorkFactory
from src.shared_kernel.value_objects.library_id import LibraryId
from src.shared_kernel.value_objects.profile_id import ProfileId


class ProfileLibraryAccessAdapter(ProfileLibraryAccessPort):
    """Resolve a profile's library ACL via the Identity Unit of Work."""

    def __init__(self, identity_uow_factory: IdentityUnitOfWorkFactory) -> None:
        self._identity_uow_factory = identity_uow_factory

    async def find_for_profile(self, profile_id: str) -> list[LibraryId]:
        """Return the typed library ids the profile may see.

        A missing profile returns an empty list — deny-all is the
        safer default than raising.
        """
        async with self._identity_uow_factory() as uow:
            profile = await uow.profiles.find_by_id(ProfileId(profile_id))
        if profile is None:
            return []
        return list(profile.allowed_library_ids)


__all__ = ["ProfileLibraryAccessAdapter"]
