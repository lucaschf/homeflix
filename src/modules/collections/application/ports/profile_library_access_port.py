"""Port for resolving the libraries a profile is allowed to read.

Shared/followed custom-list reads must filter items through the
*follower's* library access (ADR-010): an owner's list may reference
titles a follower's profile can't see, and a kids profile must never
reach restricted titles via a followed list. This port is the surface
through which Collections asks the Identity BC "what may this profile
see?". The adapter lives in ``collections.infrastructure.acl``.

Mirrors ``media.application.ports.ProfileLibraryAccessPort`` — the
same contract, re-declared locally so Collections doesn't import from
the Media BC (ADR-009).
"""

from abc import ABC, abstractmethod

from src.shared_kernel.value_objects.library_id import LibraryId


class ProfileLibraryAccessPort(ABC):
    """Lookup the library ACL for a single profile."""

    @abstractmethod
    async def find_for_profile(self, profile_id: str) -> list[LibraryId]:
        """Return the library ids ``profile_id`` may see.

        Args:
            profile_id: Prefixed external id (``prf_xxx``).

        Returns:
            The profile's ``allowed_library_ids`` as typed
            ``LibraryId`` values. An empty list means deny-all (the
            profile may see nothing); a missing profile also returns
            an empty list — the safer default than raising.
        """
        ...


__all__ = ["ProfileLibraryAccessPort"]
