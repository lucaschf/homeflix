"""Access token repository interface and its read DTOs."""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from src.modules.identity.domain.entities.profile import Profile
from src.modules.identity.domain.services.parental_gate import LockoutPolicy
from src.shared_kernel.value_objects.age_rating import AgeRating
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


@dataclass(frozen=True)
class ParentalSessionState:
    """Parental-control state of one session, i.e. one device (ADR-035).

    Attributes:
        user_id: External ID of the user owning this session.
        current_profile_id: External ID of the profile selected on the
            session, or ``None``. Read as stored: it may point at a
            soft-deleted profile, which the gate must not mistake for
            "no profile selected".
        failed_attempts: Wrong PINs counted towards the next lock.
        lockouts: The session's step on the lockout ladder.
        locked_until: End of the **last** lock, kept after it passes
            because the ladder decays from it. The session is locked
            while this is later than now.
        unlock_until: End of the unlock window opened by a correct PIN, or
            ``None``.
    """

    user_id: UserId
    current_profile_id: ProfileId | None
    failed_attempts: int
    lockouts: int
    locked_until: datetime | None
    unlock_until: datetime | None


@dataclass(frozen=True)
class ParentalSessionSnapshot:
    """A session's parental state and its account's live profiles, read as one state.

    Attributes:
        state: The session's parental state.
        account_profiles: The live profiles of the account owning the session,
            ordered by name.
    """

    state: ParentalSessionState
    account_profiles: Sequence[Profile]


@dataclass(frozen=True)
class PinAttemptReservation:
    """Outcome of reserving one PIN attempt on a session.

    Attributes:
        granted: Whether the attempt was counted and the PIN may be checked.
            ``False`` means a lock is in force (or the session is gone):
            the PIN must not be checked.
        failed_attempts: The session's attempt counter after the
            reservation, including this attempt when granted.
        locked_until: When denied, the end of the lock in force — ``None``
            only when no session has the token. When granted, the end of
            the lock this very attempt started, or ``None`` if it started
            none.
    """

    granted: bool
    failed_attempts: int
    locked_until: datetime | None


class AccessTokenRepository(ABC):
    """Repository interface for ``access_tokens``.

    Covers the operations our domain code needs (read snapshot, switch
    profile, cleanup, parental unlock and lockout). FastAPI Users' own
    auth flow goes through its ``SQLAlchemyAccessTokenDatabase`` adapter
    directly — the two share the underlying table without conflict.

    Every parental write is one conditional statement on the session row,
    so concurrent requests on the same device cannot race each other past
    the lockout or spend one unlock twice.
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
        *,
        expected_limit: AgeRating | None,
    ) -> bool:
        """Set the active profile for an existing session, atomically (compare-and-set).

        Internally resolves ``profile_id`` to the row's internal UUID
        before issuing the UPDATE. Passing ``None`` clears the current
        profile (used when a profile is deleted while it was active in
        a sibling session — enforced via ``ON DELETE SET NULL``, but
        callable explicitly too).

        Entering a profile is one conditional write: it takes effect only
        while the target is live and still has ``expected_limit``, the
        limit the parental gate decided on. A limit changed after the gate
        read it (a widening that already detached the sessions on the
        profile) makes the call return ``False`` instead of landing the
        session on a profile the gate never saw (ADR-035, Amendment 7 D9).

        The same UPDATE closes the session's parental unlock window: every
        switch, whatever its target, starts the new profile without a
        leftover unlock (ADR-035, Amendment 7 D9).

        Args:
            token: The session token to update.
            profile_id: The profile to make active, or ``None``.
            expected_limit: The target's maturity limit as the caller read
                it; ``None`` is unrestricted. Ignored when ``profile_id`` is
                ``None``.

        Returns:
            ``True`` if the row was updated; ``False`` if no session with
            that token exists, or the target is soft-deleted or no longer
            has ``expected_limit``.

        Raises:
            ValueError: If no profile has ``profile_id``.
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

    @abstractmethod
    async def get_parental_state(self, token: str) -> ParentalSessionState | None:
        """Read the session's parental-control state.

        Args:
            token: The session token.

        Returns:
            The state, or ``None`` if the token is unknown.
        """
        ...

    @abstractmethod
    async def get_parental_snapshot(self, token: str) -> ParentalSessionSnapshot | None:
        """Read the session's parental state and its account's live profiles, together.

        Exists for a gate that decides on both without the account lock
        (``UserRepository.lock_for_parental_change``): read apart, a change
        committed between the two reads — a widening of the session's
        profile, which also detaches the session — would combine the session
        as it was before with the profiles as they are after, a state no
        request ever saw. Read together, both come from one snapshot.

        Args:
            token: The session token.

        Returns:
            The snapshot, or ``None`` if the token is unknown.
        """
        ...

    @abstractmethod
    async def reserve_pin_attempt(
        self,
        token: str,
        *,
        now: datetime,
        policy: LockoutPolicy,
    ) -> PinAttemptReservation:
        """Count one PIN attempt, unless the session is locked, atomically.

        One conditional write, before the PIN is checked: a lock that has
        passed restarts the attempt counter, a ladder quiet for
        ``policy.decay`` after its last lock returns to step zero, and the
        attempt that reaches ``policy.max_attempts`` starts a lock of
        ``policy.lock_duration(step)`` and climbs one step. The caller must
        commit the reservation before raising anything, or a rollback would
        hand the attempt back.

        Args:
            token: The session token.
            now: The current time (timezone-aware).
            policy: The lockout ladder to apply.

        Returns:
            The reservation; see :class:`PinAttemptReservation`.
        """
        ...

    @abstractmethod
    async def record_pin_success(
        self,
        token: str,
        *,
        now: datetime,
        unlock_until: datetime,
    ) -> None:
        """Record a correct PIN: open the unlock window and clear the attempts.

        Also ends a lock in force — the one the correct attempt itself may
        have started — while keeping the end of the last lock and the
        ladder step, which a correct PIN never lowers (Amendment 7 D4).

        Args:
            token: The session token.
            now: The current time (timezone-aware).
            unlock_until: End of the unlock window.
        """
        ...

    @abstractmethod
    async def consume_unlock(self, token: str, *, now: datetime) -> bool:
        """Spend the session's unlock window, atomically.

        Args:
            token: The session token.
            now: The current time (timezone-aware).

        Returns:
            ``True`` if a window still open at ``now`` was closed by this
            call; ``False`` if there was none, it had passed, or a
            concurrent call spent it first.
        """
        ...

    @abstractmethod
    async def clear_unlock(self, token: str) -> None:
        """Close the session's unlock window, if any.

        Touches only the window: the attempt counter, the lock and the
        ladder are left as they are, so closing the window is never a way
        to earn more attempts.

        Args:
            token: The session token.
        """
        ...

    @abstractmethod
    async def detach_profile_sessions(self, profile_id: ProfileId, *, except_token: str) -> int:
        """Drop every other session off a profile that was just widened.

        The switch guard only checks a profile's limit when a session enters
        it, so a device already on a profile would keep it once widened
        (ADR-035, Amendment 7 D9 and D12). Each matching session loses its
        selected profile and its unlock window, and nothing else: the attempt
        counter, the lock and the ladder stay, so being detached never earns
        PIN attempts. A detached device is back to "no profile selected".

        Args:
            profile_id: The widened profile.
            except_token: The session making the change, which stays on it.

        Returns:
            How many sessions were detached.
        """
        ...


__all__ = [
    "AccessTokenRepository",
    "AccessTokenSnapshot",
    "ParentalSessionSnapshot",
    "ParentalSessionState",
    "PinAttemptReservation",
]
