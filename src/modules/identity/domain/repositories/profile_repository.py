"""Profile repository interface."""

from abc import ABC, abstractmethod
from collections.abc import Sequence

from src.modules.identity.domain.entities.profile import Profile
from src.shared_kernel.value_objects.age_rating import AgeRating
from src.shared_kernel.value_objects.profile_id import ProfileId
from src.shared_kernel.value_objects.user_id import UserId


class ProfileRepository(ABC):
    """Repository interface for the ``Profile`` aggregate.

    Profile is modelled as a separate aggregate (not a child of User)
    so authentication checks do not pay the cost of hydrating profiles
    on every request. Cross-BC consumers reference only ``ProfileId``;
    ownership invariants are enforced at use-case boundaries.
    """

    @abstractmethod
    async def save(self, profile: Profile) -> Profile | None:
        """Persist a profile (create or update).

        Generates an external ID on insert. Caller's ``user_id`` must
        reference an existing user — the SQLAlchemy implementation
        resolves it to the internal UUID before writing.

        The maturity limit is written only on insert. On an existing
        profile it is left as stored, whatever the entity carries: only
        :meth:`set_maturity_limit` changes it, so an entity read before a
        concurrent limit change (a rename, an avatar) cannot write the old
        limit back (ADR-035).

        A soft-deleted profile is never restored, and never written: an
        entity read before a concurrent delete (a rename, an avatar) cannot
        bring the profile back with its limit, possibly after the PIN that
        protected the limit was removed (ADR-035, Amendment 7 D2).

        Args:
            profile: The profile to save.

        Returns:
            The saved profile, re-read from the database; ``None`` when the
            profile exists but is soft-deleted, including when it is deleted
            before this write lands.
        """
        ...

    @abstractmethod
    async def set_maturity_limit(
        self,
        profile_id: ProfileId,
        *,
        expected: AgeRating | None,
        new: AgeRating | None,
    ) -> bool:
        """Change a live profile's maturity limit, atomically (compare-and-set).

        One conditional write that also keeps the stored kids flag derived.
        It takes effect only while the profile is live, still has the
        ``expected`` limit, and, when ``new`` is a limit, its account has a
        parental PIN (ADR-035, Amendment 7 D2). The caller decides what to
        do on ``False`` by re-reading in the same transaction.

        Args:
            profile_id: The profile's external ID.
            expected: The limit the caller read and decided on; ``None`` is
                unrestricted.
            new: The limit to store; ``None`` removes it.

        Returns:
            ``True`` when this call changed the row; ``False`` when the
            profile is missing or soft-deleted, its limit is no longer
            ``expected``, or ``new`` is a limit and the account has no PIN.
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
