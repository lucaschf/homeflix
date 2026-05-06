"""Access token repository interface and its read DTO."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

from src.shared_kernel.value_objects.profile_id import ProfileId
from src.shared_kernel.value_objects.user_id import UserId


@dataclass(frozen=True)
class AccessTokenSnapshot:
    """Read-only projection of a session row exposed to the domain.

    The on-disk ``access_tokens`` table stores UUIDs as foreign keys
    (so that FastAPI Users' ``DatabaseStrategy`` can use them natively).
    Domain code consumes prefixed external IDs only — ``user_id`` and
    ``current_profile_id`` here are the translated VOs. Translation
    happens in ``SqlAlchemyAccessTokenRepository`` via JOINs on the
    users / profiles tables, so the rest of the system never sees a
    raw UUID.

    Attributes:
        token: The opaque session token (also the row's primary key).
        user_id: External ID of the user owning this session.
        current_profile_id: External ID of the active profile, or
            ``None`` if the user has not selected a profile in this
            session (post-login, pre-profile-picker).
        created_at: Session issue time (used for absolute-expiration
            checks and the cleanup job).
    """

    token: str
    user_id: UserId
    current_profile_id: ProfileId | None
    created_at: datetime


class AccessTokenRepository(ABC):
    """Repository interface for ``access_tokens``.

    Covers the operations our domain code needs (read snapshot, switch
    profile, cleanup). FastAPI Users' own auth flow goes through its
    ``SQLAlchemyAccessTokenDatabase`` adapter directly — the two share
    the underlying table without conflict.
    """

    @abstractmethod
    async def get_by_token(self, token: str) -> AccessTokenSnapshot | None:
        """Resolve a session token to its (user, current_profile) pair.

        Args:
            token: The opaque token from the cookie.

        Returns:
            Snapshot with prefixed external IDs, or ``None`` if the
            token is unknown.
        """
        ...

    @abstractmethod
    async def update_current_profile(
        self,
        token: str,
        profile_id: ProfileId | None,
    ) -> bool:
        """Set the active profile for an existing session.

        Internally resolves ``profile_id`` to the row's internal UUID
        before issuing the UPDATE. Passing ``None`` clears the current
        profile (used when a profile is deleted while it was active in
        a sibling session — enforced via ``ON DELETE SET NULL``, but
        callable explicitly too).

        Args:
            token: The session token to update.
            profile_id: The profile to make active, or ``None``.

        Returns:
            ``True`` if a row was updated, ``False`` if no session
            with that token exists.
        """
        ...

    @abstractmethod
    async def delete_older_than(self, cutoff: datetime) -> int:
        """Remove sessions whose ``created_at`` is older than ``cutoff``.

        Used by the periodic cleanup job (wired in a later PR). Hard
        DELETE — these rows have no soft-delete semantics.

        Args:
            cutoff: Sessions strictly older than this timestamp are
                removed.

        Returns:
            Number of rows deleted.
        """
        ...


__all__ = ["AccessTokenRepository", "AccessTokenSnapshot"]
