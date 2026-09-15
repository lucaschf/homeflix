"""Internal helper: the parental gate on the profile operations (ADR-035, Amendment 7).

Switching, creating, updating and deleting a profile share how the gate is
read and spent; the rules deciding when switching, creating or updating needs
an unlock live in :class:`ParentalGate`, and deleting needs one whenever the
account has a PIN (Amendment 8). Everything here runs inside the operation's
own Unit of Work, before its write, so a refused operation writes nothing and
an unlock is spent only together with the change it pays for.

**The account lock.** Each of those operations opens its Unit of Work with
:func:`lock_account`, before any read — the gate's included — and keeps it until
the Unit of Work ends (``UserRepository.lock_for_parental_change``). Setting and
removing the PIN take the same lock for their write. So the session, the
profiles and the PIN that :func:`read_gate_session` reads form one state that no
other of these operations can change before this one commits: the gate never
mixes a session read before a concurrent change with profiles read after it,
and the PIN it read is still the PIN when the change lands. The
compare-and-sets of the individual writes stay underneath, as defence in depth.
"""

from dataclasses import dataclass
from datetime import UTC, datetime

from src.modules.identity.application.errors import UserNotFoundException
from src.modules.identity.application.unit_of_work import IdentityUnitOfWork
from src.modules.identity.domain.errors import (
    ParentalPinNotConfiguredError,
    ParentalPinRequiredError,
)
from src.modules.identity.domain.services.parental_gate import ParentalGate
from src.shared_kernel.value_objects.age_rating import AgeRating
from src.shared_kernel.value_objects.profile_id import ProfileId
from src.shared_kernel.value_objects.user_id import UserId


def utc_now() -> datetime:
    """Return the current time in UTC, the default clock of the gated use cases."""
    return datetime.now(UTC)


@dataclass(frozen=True)
class GateSession:
    """What the parental gate knows about the session behind a profile operation.

    Attributes:
        session_token: The caller's session token, or ``None`` outside a
            session.
        pin_configured: Whether the account has a parental PIN. Without one
            the gate is inert.
        active_profile_id: The profile selected on the session as stored, so
            possibly soft-deleted; ``None`` when none is selected or the
            session could not be read.
        limit: The limit the session acts under, as
            :meth:`ParentalGate.session_limit` computes it; ``None`` without a
            PIN. A session that could not be read acts under ``AgeRating(0)``.
        verified: Whether the session row was found and belongs to the
            caller. Only a verified session may spend an unlock.
    """

    session_token: str | None
    pin_configured: bool
    active_profile_id: ProfileId | None
    limit: AgeRating | None
    verified: bool


async def lock_account(uow: IdentityUnitOfWork, caller_id: UserId) -> None:
    """Take the account lock of a gated profile operation (see the module docstring).

    Must be the first statement of the operation's Unit of Work. Costs one
    query, with or without a PIN.

    Args:
        uow: The operation's active Unit of Work, before any read.
        caller_id: The account performing the operation.

    Raises:
        UserNotFoundException: If the account no longer exists (HTTP 404).
    """
    if not await uow.users.lock_for_parental_change(caller_id):
        raise UserNotFoundException.for_resource("User", caller_id.value)


async def read_gate_session(
    uow: IdentityUnitOfWork,
    caller_id: UserId,
    session_token: str | None,
) -> GateSession:
    """Read what the parental gate needs about the caller's session.

    Only after :func:`lock_account` in the same Unit of Work: its reads are
    then one consistent state. Without a PIN this costs one query, the
    account; with one, also the session's parental state and the account's
    live profiles.

    Args:
        uow: The operation's active Unit of Work.
        caller_id: The account performing the operation.
        session_token: The caller's session token, or ``None`` outside a
            session.

    Returns:
        The session as the gate sees it.

    Raises:
        UserNotFoundException: If the account no longer exists.
    """
    user = await uow.users.find_by_id(caller_id)
    if user is None:
        raise UserNotFoundException.for_resource("User", caller_id.value)
    if not user.has_parental_pin:
        return GateSession(
            session_token=session_token,
            pin_configured=False,
            active_profile_id=None,
            limit=None,
            verified=False,
        )

    state = None
    if session_token is not None:
        state = await uow.access_tokens.get_parental_state(session_token)
    profiles = await uow.profiles.find_by_user(caller_id)
    if state is None or state.user_id != caller_id:
        # Nothing proves which profile this session is on: act under the
        # strictest limit, with no unlock to spend.
        return GateSession(
            session_token=session_token,
            pin_configured=True,
            active_profile_id=None,
            limit=AgeRating(AgeRating.MIN),
            verified=False,
        )
    return GateSession(
        session_token=session_token,
        pin_configured=True,
        active_profile_id=state.current_profile_id,
        limit=ParentalGate.session_limit(state.current_profile_id, profiles),
        verified=True,
    )


def refuse_limit_without_pin(
    session: GateSession,
    *,
    before: AgeRating | None,
    after: AgeRating | None,
) -> None:
    """Refuse to write a maturity limit on an account without a PIN (Amendment 7 D2).

    Only a limit the operation writes counts: keeping a profile's limit as it
    was, or removing it, is not writing one.

    Args:
        session: The session as the gate sees it.
        before: The profile's limit before the operation; ``None`` for a new
            profile.
        after: The limit the operation leaves.

    Raises:
        ParentalPinNotConfiguredError: If the account has no PIN and the
            operation sets a limit (HTTP 409).
    """
    if session.pin_configured or after is None:
        return
    if before is not None and before.value == after.value:
        return
    raise ParentalPinNotConfiguredError(
        message="A maturity limit needs a parental PIN on the account",
    )


async def spend_unlock(uow: IdentityUnitOfWork, session: GateSession, *, now: datetime) -> str:
    """Spend the session's unlock window for a gated profile operation, atomically.

    Called before the operation writes, inside its Unit of Work: the unlock is
    consumed by one conditional statement, so two operations racing on one
    window cannot both pass, and a write that fails afterwards rolls the
    window back with it (Amendment 7 D9).

    Args:
        uow: The operation's active Unit of Work.
        session: The session as the gate sees it.
        now: The current time (timezone-aware).

    Returns:
        The token of the session whose unlock was spent.

    Raises:
        ParentalPinRequiredError: If the session has no unlock open at
            ``now``, or could not be verified (HTTP 403, never 401).
    """
    token = session.session_token
    if (
        not session.verified
        or token is None
        or not await uow.access_tokens.consume_unlock(token, now=now)
    ):
        raise ParentalPinRequiredError(
            message="This profile change needs the parental PIN on this device",
        )
    return token


__all__ = [
    "GateSession",
    "lock_account",
    "read_gate_session",
    "refuse_limit_without_pin",
    "spend_unlock",
    "utc_now",
]
