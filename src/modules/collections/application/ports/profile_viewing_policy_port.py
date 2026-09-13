"""Port for resolving what a profile may see, for Collections.

Shared and followed custom-list reads must filter items through the
*follower's* own policy (ADR-010): an owner's list may reference titles
the follower cannot see, and a restricted profile must never reach
unsuitable titles through a followed list. This port is the surface
through which Collections asks the Identity BC "what may this profile
see?".

Mirrors ``media.application.ports.ProfileViewingPolicyPort`` — the same
contract, re-declared locally so Collections does not import from the
Media BC (ADR-009). Two copies of the same abstract port today (Media
and Collections), with a third expected when ``watch_progress`` gains
the gate, is conformance with that ADR, not duplication to be factored
away.
"""

from abc import ABC, abstractmethod

from src.shared_kernel.content_policy import ViewingPolicy
from src.shared_kernel.value_objects.profile_id import ProfileId


class ProfileViewingPolicyPort(ABC):
    """Lookup the viewing policy for a single profile."""

    @abstractmethod
    async def find_for_profile(self, profile_id: ProfileId) -> ViewingPolicy:
        """Return what ``profile_id`` is allowed to see.

        Args:
            profile_id: The profile whose policy to resolve.

        Returns:
            The profile's two visibility axes. A missing profile gets
            an empty ACL — deny-all, the safer default than raising.
        """
        ...


__all__ = ["ProfileViewingPolicyPort"]
