"""Port for resolving the libraries a profile is allowed to read.

Per ADR-010, every catalog list endpoint filters by the caller's
``Profile.allowed_library_ids``. Media doesn't own the profile data —
this port is the only surface through which it reaches into the
identity BC. The adapter lives in ``media.infrastructure.acl``.

The port returns ``list[LibraryId]`` (ADR-018). ``LibraryId`` lives in
the shared_kernel, so the typed contract does not couple media to the
identity (or library) BC — the "no foreign domain types" rule from
ADR-009 still holds. An earlier revision returned plain ``list[str]``;
that predates ``LibraryId``'s promotion to the shared_kernel.

See ADR-009 for the cross-BC read port pattern.
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
            profile may see nothing). A missing profile also returns
            an empty list — the safer default than raising, because
            the caller's intent is "what can this profile see?" and
            the answer is "nothing" if it doesn't exist.
        """
        ...


__all__ = ["ProfileLibraryAccessPort"]
