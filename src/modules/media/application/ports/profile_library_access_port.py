"""Port for resolving the libraries a profile is allowed to read.

Per ADR-010, every catalog list endpoint filters by the caller's
``Profile.allowed_library_ids``. Media doesn't own the profile data —
this port is the only surface through which it reaches into the
identity BC. The adapter lives in ``media.infrastructure.acl``.

The port returns a plain ``list[str]`` rather than a frozen DTO
because the only datum it carries is the list itself; wrapping
adds zero invariants. The "no domain types" rule from ADR-009
still holds — strings are primitive.

See ADR-009 for the cross-BC read port pattern.
"""

from abc import ABC, abstractmethod


class ProfileLibraryAccessPort(ABC):
    """Lookup the library ACL for a single profile."""

    @abstractmethod
    async def find_for_profile(self, profile_id: str) -> list[str]:
        """Return the prefixed library_ids ``profile_id`` may see.

        Args:
            profile_id: Prefixed external id (``prf_xxx``).

        Returns:
            The profile's ``allowed_library_ids``. An empty list
            means deny-all (the profile may see nothing). A missing
            profile also returns an empty list — the safer default
            than raising, because the caller's intent is "what can
            this profile see?" and the answer is "nothing" if it
            doesn't exist.
        """
        ...


__all__ = ["ProfileLibraryAccessPort"]
