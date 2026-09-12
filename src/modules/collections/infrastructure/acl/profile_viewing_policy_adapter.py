"""Adapter implementing Collections' ``ProfileViewingPolicyPort``.

One of two adapters in the Collections BC that read through Identity's
Unit of Work — the other is ``profile_lookup_adapter.py``; the
presentation layer imports only Identity's public ``resolve_profile_id``
dependency (ADR-009).
"""

from src.modules.collections.application.ports.profile_viewing_policy_port import (
    ProfileViewingPolicyPort,
)
from src.modules.identity.application.unit_of_work import (
    IdentityUnitOfWorkFactory,
)
from src.shared_kernel.content_policy import ViewingPolicy
from src.shared_kernel.value_objects.profile_id import ProfileId


class ProfileViewingPolicyAdapter(ProfileViewingPolicyPort):
    """Resolve a profile's viewing policy via the Identity Unit of Work."""

    def __init__(self, identity_uow_factory: IdentityUnitOfWorkFactory) -> None:
        self._identity_uow_factory = identity_uow_factory

    async def find_for_profile(self, profile_id: ProfileId) -> ViewingPolicy:
        """Return the profile's two visibility axes; deny-all when missing."""
        async with self._identity_uow_factory() as uow:
            profile = await uow.profiles.find_by_id(profile_id)

        if profile is None:
            return ViewingPolicy(allowed_library_ids=[])

        return ViewingPolicy(allowed_library_ids=profile.allowed_library_ids)


__all__ = ["ProfileViewingPolicyAdapter"]
