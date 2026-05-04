"""Adapter implementing ``ProfileLibraryAccessPort`` via the identity UoW.

This is the only file in the Media BC that imports from the Identity
BC. Above the adapter, the use cases only see the abstract port —
the cross-BC boundary stays explicit, per ADR-009.
"""

from src.modules.identity.application.unit_of_work import (
    IdentityUnitOfWorkFactory,
)
from src.modules.media.application.ports.profile_library_access_port import (
    ProfileLibraryAccessPort,
)
from src.shared_kernel.value_objects.profile_id import ProfileId


class ProfileLibraryAccessAdapter(ProfileLibraryAccessPort):
    """Resolve a profile's library ACL via the Identity Unit of Work."""

    def __init__(self, identity_uow_factory: IdentityUnitOfWorkFactory) -> None:
        self._identity_uow_factory = identity_uow_factory

    async def find_for_profile(self, profile_id: str) -> list[str]:
        """Return the prefixed library_ids the profile may see.

        A missing profile returns an empty list — deny-all is the
        safer default than raising. The use cases short-circuit on
        an empty list and skip the catalog UoW altogether, so this
        also keeps cost down for unauthenticated requests served
        through the transitional fallback when the configured
        default profile no longer exists.
        """
        async with self._identity_uow_factory() as uow:
            profile = await uow.profiles.find_by_id(ProfileId(profile_id))
        if profile is None:
            return []
        return list(profile.allowed_library_ids)


__all__ = ["ProfileLibraryAccessAdapter"]
