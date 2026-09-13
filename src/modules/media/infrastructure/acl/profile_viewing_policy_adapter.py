"""Adapter implementing ``ProfileViewingPolicyPort`` via the identity UoW.

One of two adapters in the Media BC that read through the Identity BC's
Unit of Work — the other is ``identity_user_count_adapter.py``; the
presentation layer imports only ``identity.presentation.public``.
Above the adapter the use cases see only the abstract port, so the
cross-BC boundary stays explicit (ADR-009).
"""

from src.modules.identity.application.unit_of_work import (
    IdentityUnitOfWorkFactory,
)
from src.modules.media.application.ports.profile_viewing_policy_port import (
    ProfileViewingPolicyPort,
)
from src.shared_kernel.content_policy import ViewingPolicy
from src.shared_kernel.value_objects.profile_id import ProfileId


class ProfileViewingPolicyAdapter(ProfileViewingPolicyPort):
    """Resolve a profile's viewing policy via the Identity Unit of Work."""

    def __init__(self, identity_uow_factory: IdentityUnitOfWorkFactory) -> None:
        self._identity_uow_factory = identity_uow_factory

    async def find_for_profile(self, profile_id: ProfileId) -> ViewingPolicy:
        """Return the profile's two visibility axes.

        A missing profile yields an empty ACL, which ``ViewingPolicy``
        reads as deny-all. That keeps the transitional fallback safe
        when a configured default profile no longer exists.
        """
        async with self._identity_uow_factory() as uow:
            profile = await uow.profiles.find_by_id(profile_id)

        if profile is None:
            return ViewingPolicy(allowed_library_ids=[])

        return ViewingPolicy(allowed_library_ids=profile.allowed_library_ids)


__all__ = ["ProfileViewingPolicyAdapter"]
