"""Domain rules of the parental gate (ADR-035, decisions 8 and 9, Amendment 7).

Pure functions over profiles, limits and times, with no I/O. The unlock use
case applies the lockout policy; the admin and profile gates read the
session's effective limit and the admin matrix from here, so each rule is
written once.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import TYPE_CHECKING

from src.shared_kernel.value_objects.age_rating import AgeRating

if TYPE_CHECKING:
    from collections.abc import Sequence

    from src.modules.identity.domain.entities.profile import Profile
    from src.shared_kernel.value_objects.profile_id import ProfileId

UNLOCK_WINDOW = timedelta(minutes=5)
"""How long a correct PIN unlocks the device that entered it, with no renewal."""


@dataclass(frozen=True)
class LockoutPolicy:
    """Per-device lockout ladder for wrong parental PINs (Amendment 7 D4).

    Every ``max_attempts`` wrong PINs lock the session for
    :meth:`lock_duration` of the current step and move it one step up. A
    correct PIN clears the attempts and ends a lock in force but never moves
    the ladder down; the ladder falls back to step zero only ``decay`` after
    the end of the last lock.

    The persistence adapter computes the same durations in SQL, so the
    parameters are whole seconds.

    Attributes:
        max_attempts: Wrong PINs that start a lock.
        base_lock: Lock length at step zero.
        max_lock: Longest lock, reached by doubling.
        decay: Quiet time after the last lock ends that resets the ladder.
    """

    max_attempts: int = 5
    base_lock: timedelta = timedelta(minutes=5)
    max_lock: timedelta = timedelta(hours=24)
    decay: timedelta = timedelta(hours=24)

    def __post_init__(self) -> None:
        """Reject a policy the ladder cannot apply.

        Raises:
            ValueError: If there is no attempt budget, a lock is not positive,
                the ceiling is below the base, the decay is negative, or a
                duration is not whole seconds.
        """
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if self.base_lock <= timedelta(0) or self.max_lock < self.base_lock:
            raise ValueError("locks must be positive, with max_lock >= base_lock")
        if self.decay < timedelta(0):
            raise ValueError("decay cannot be negative")
        for duration in (self.base_lock, self.max_lock, self.decay):
            if duration.microseconds:
                raise ValueError("lockout durations must be whole seconds")

    @property
    def saturation_step(self) -> int:
        """The first ladder step whose doubled lock reaches ``max_lock``.

        From this step on every lock lasts ``max_lock``; bounding the
        exponent here keeps the doubling from overflowing, in Python and in
        SQL, however high the ladder climbs.
        """
        step = 0
        while self.base_lock * (1 << step) < self.max_lock:
            step += 1
        return step

    def lock_duration(self, lockouts: int) -> timedelta:
        """Return how long a lock started at ladder step ``lockouts`` lasts.

        ``min(base_lock * 2**lockouts, max_lock)``.

        Args:
            lockouts: Locks already on the ladder before this one.

        Returns:
            The lock length.

        Raises:
            ValueError: If ``lockouts`` is negative.

        Example:
            >>> [LockoutPolicy().lock_duration(n).total_seconds() for n in (0, 1, 9)]
            [300.0, 600.0, 86400.0]
        """
        if lockouts < 0:
            raise ValueError("lockouts cannot be negative")
        return min(self.base_lock * (1 << min(lockouts, self.saturation_step)), self.max_lock)


class AdminAccess(StrEnum):
    """Whether a session may use administrator authority right now."""

    GRANTED = "granted"
    SUSPENDED = "suspended"


class ParentalGate:
    """Rules deciding when the parental PIN stands between a session and an action.

    Each rule works on the account's live profiles, as the profile
    repository lists them: a session whose selected profile is missing from
    that list points at a soft-deleted profile.
    """

    @staticmethod
    def session_limit(
        active_profile_id: ProfileId | None,
        account_profiles: Sequence[Profile],
    ) -> AgeRating | None:
        """Return the maturity limit a session acts under.

        Args:
            active_profile_id: The profile selected on the session, or
                ``None`` when none is selected.
            account_profiles: The account's live profiles.

        Returns:
            The selected profile's limit when it is live; ``AgeRating(0)``
            when the selected profile was deleted, so a stale session never
            reads as unrestricted; with no profile selected, the lowest limit
            among the live profiles (Amendment 7 D1), or ``None`` when none
            has a limit.
        """
        if active_profile_id is not None:
            for profile in account_profiles:
                if profile.id == active_profile_id:
                    return profile.maturity_limit
            return AgeRating(AgeRating.MIN)

        limits = [p.maturity_limit for p in account_profiles if p.maturity_limit is not None]
        return min(limits, key=lambda limit: limit.value) if limits else None

    @staticmethod
    def exceeds(target: AgeRating | None, baseline: AgeRating | None) -> bool:
        """Whether moving from ``baseline`` to ``target`` widens what may be watched.

        Args:
            target: The limit after the change; ``None`` is unrestricted.
            baseline: The limit before the change; ``None`` is unrestricted.

        Returns:
            ``False`` when the baseline is unrestricted; ``True`` when only
            the target is; otherwise whether the target is the higher age.

        Example:
            >>> ParentalGate.exceeds(AgeRating(14), AgeRating(12))
            True
            >>> ParentalGate.exceeds(AgeRating(12), AgeRating(12))
            False
        """
        if baseline is None:
            return False
        if target is None:
            return True
        return target.value > baseline.value

    @staticmethod
    def admin_access(
        *,
        pin_configured: bool,
        active_profile_id: ProfileId | None,
        account_profiles: Sequence[Profile],
        unlock_until: datetime | None,
        now: datetime,
        is_write: bool,
    ) -> AdminAccess:
        """Decide whether an administrator's session may use admin authority.

        Without a PIN the gate is inert. With one, a valid unlock on the
        session grants everything; otherwise authority is suspended whenever
        the session acts under a limit, and admin writes are also suspended
        when any live profile of the account has a limit (Amendment 7 D10).

        Args:
            pin_configured: Whether the account has a parental PIN.
            active_profile_id: The profile selected on the session, if any.
            account_profiles: The account's live profiles.
            unlock_until: End of the session's unlock window, if any.
            now: The current time.
            is_write: Whether the request changes state.

        Returns:
            ``AdminAccess.GRANTED`` or ``AdminAccess.SUSPENDED``.
        """
        if not pin_configured:
            return AdminAccess.GRANTED
        if unlock_until is not None and unlock_until > now:
            return AdminAccess.GRANTED
        if ParentalGate.session_limit(active_profile_id, account_profiles) is not None:
            return AdminAccess.SUSPENDED
        if is_write and any(p.maturity_limit is not None for p in account_profiles):
            return AdminAccess.SUSPENDED
        return AdminAccess.GRANTED


__all__ = ["UNLOCK_WINDOW", "AdminAccess", "LockoutPolicy", "ParentalGate"]
