"""Port for resolving what a profile may see in the catalog.

Every catalog read filters by the caller's profile, on two axes that
compose by AND: the libraries the profile may reach, and the highest
content rating it may watch (ADR-035). Media does not own profile data —
this port is the surface through which catalog reads reach into the
Identity BC, and the adapter lives in ``media.infrastructure.acl``.

Both axes travel in one :class:`ViewingPolicy` rather than as two
lookups: they are read together on every request, and splitting them
would mean two round-trips to answer one question. ``ViewingPolicy`` and
``LibraryId`` live in the shared kernel, so the typed contract does not
couple Media to the Identity BC — the "no foreign domain types" rule of
ADR-009 still holds.

Replaces the earlier library-only access port, which returned only
``list[LibraryId]`` and took an untyped ``profile_id: str``.

See ADR-009 for the cross-BC read port pattern.
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
            The profile's two visibility axes. A missing profile gets a
            policy with an empty ACL — deny-all, which is the safer
            default than raising, because the caller's question is
            "what may this profile see?" and the answer for a profile
            that does not exist is "nothing".
        """
        ...


__all__ = ["ProfileViewingPolicyPort"]
