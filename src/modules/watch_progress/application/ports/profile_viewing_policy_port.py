"""Port for resolving what a profile may see, for Watch Progress.

Progress rows point at catalog titles, and a profile must not reach a
title it cannot see through its own progress: not on the "Continue
Watching" row, not by reading a single row back, and not by recording
progress on it. This port is the surface through which Watch Progress
asks the Identity BC "what may this profile see?".

Mirrors ``media.application.ports.ProfileViewingPolicyPort`` and
``collections.application.ports.ProfileViewingPolicyPort`` — the same
contract, re-declared locally so Watch Progress does not import from
another BC (ADR-009, ADR-035 §6).
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
