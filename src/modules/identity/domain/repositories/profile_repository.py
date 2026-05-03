"""Profile repository interface."""

from abc import ABC, abstractmethod
from collections.abc import Sequence

from src.modules.identity.domain.entities.profile import Profile
from src.modules.identity.domain.value_objects.profile_id import ProfileId
from src.modules.identity.domain.value_objects.user_id import UserId


class ProfileRepository(ABC):
    """Repository interface for the ``Profile`` aggregate.

    Profile is modelled as a separate aggregate (not a child of User)
    so authentication checks do not pay the cost of hydrating profiles
    on every request. Cross-BC consumers reference only ``ProfileId``;
    ownership invariants are enforced at use-case boundaries.
    """

    @abstractmethod
    async def save(self, profile: Profile) -> Profile:
        """Persist a profile (create or update).

        Generates an external ID on insert. Caller's ``user_id`` must
        reference an existing user — the SQLAlchemy implementation
        resolves it to the internal UUID before writing.

        Args:
            profile: The profile to save.

        Returns:
            The saved profile, re-read from the database.
        """
        ...

    @abstractmethod
    async def find_by_id(self, profile_id: ProfileId) -> Profile | None:
        """Look up a profile by its prefixed external ID.

        Args:
            profile_id: The profile's external ID (``prf_xxx``).

        Returns:
            The profile if found and not soft-deleted, ``None`` otherwise.
        """
        ...

    @abstractmethod
    async def find_by_user(self, user_id: UserId) -> Sequence[Profile]:
        """List all profiles owned by the given user, ordered by name.

        Args:
            user_id: The owning user's external ID.

        Returns:
            Sequence of profiles (may be empty).
        """
        ...

    @abstractmethod
    async def count_for_user(self, user_id: UserId) -> int:
        """Count non-deleted profiles owned by the user.

        Used by ``DeleteProfileUseCase`` to enforce the "cannot delete
        the last profile" invariant.

        Args:
            user_id: The owning user's external ID.

        Returns:
            Number of active profiles for the user.
        """
        ...

    @abstractmethod
    async def delete(self, profile_id: ProfileId) -> bool:
        """Soft-delete a profile.

        Args:
            profile_id: The profile's external ID.

        Returns:
            ``True`` if the profile was found and deleted, ``False``
            if it didn't exist or was already deleted.
        """
        ...


__all__ = ["ProfileRepository"]
