"""SwitchProfileUseCase."""

from collections.abc import Callable
from datetime import datetime

from src.modules.identity.application.dtos.identity_dtos import SwitchProfileInput
from src.modules.identity.application.errors import (
    NoActiveSessionError,
    ProfileNotFoundException,
    ProfileOwnershipViolation,
)
from src.modules.identity.application.unit_of_work import IdentityUnitOfWorkFactory
from src.modules.identity.application.use_cases._profile_gate import (
    lock_account,
    read_gate_session,
    spend_unlock,
    utc_now,
)
from src.modules.identity.domain.errors import ParentalPinRequiredError
from src.modules.identity.domain.services.parental_gate import ParentalGate
from src.shared_kernel.value_objects.profile_id import ProfileId
from src.shared_kernel.value_objects.user_id import UserId


class SwitchProfileUseCase:
    """Change the active profile carried by the caller's session.

    Persists the chosen profile in ``access_tokens.current_profile_id``
    so subsequent requests resolve to it via ``get_current_profile``.
    The cookie itself is not re-emitted — the row update is the only
    side effect, which means multi-device sessions can each carry
    their own active profile (per ADR-011).

    Enforces, in this order:

    - **Account exists**: the caller's account is locked first (see
      *Atomicity*); a deleted one → ``UserNotFoundException`` (HTTP 404).
    - **Profile exists**: missing target → :class:`ProfileNotFoundException`
      (HTTP 404).
    - **Ownership**: target must belong to the caller →
      :class:`ProfileOwnershipViolation` (HTTP 403).
    - **Parental gate** (ADR-035, Amendment 7): on an account with a
      parental PIN, entering a profile whose limit exceeds the one the
      session acts under needs an unlock on this device, which the switch
      spends → ``ParentalPinRequiredError`` (HTTP 403). It comes after
      ownership, so it tells nothing about another account's PIN, and
      before the session row is written.
    - **Session exists**: the caller's session row must be present —
      a missing token means the cookie was tampered with or already
      revoked → :class:`NoActiveSessionError` (HTTP 401).

    Every switch closes the device's unlock window, whatever the target.

    **Atomicity.** The Unit of Work opens with the account lock
    (``lock_account``), so every read below — the target, the session and
    the account's profiles — is one state that no other profile or PIN
    change of the account can alter before the switch commits: a widening
    of the current profile cannot slip between the session read and the
    profiles read, nor a widening of the target between the gate and the
    write. Underneath, as defence in depth, the write is still a
    compare-and-set on the target's limit
    (``update_current_profile(..., expected_limit=...)``). When it fails
    with the session still present, the target and the gate are read again
    and the switch is attempted once more, so a change that keeps it
    allowed (a narrowing) still lets it through; if it fails again the
    switch is refused with ``ParentalPinRequiredError``. The retry is
    bounded to one: the failed statement already holds the write lock, so
    the second reads exactly what its statement will see. An unlock spent
    on the first attempt pays for the second, which is in the same
    transaction.
    """

    def __init__(
        self,
        uow_factory: IdentityUnitOfWorkFactory,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    async def execute(self, input_dto: SwitchProfileInput) -> None:
        """Persist the target profile as the active one in the caller's session.

        Args:
            input_dto: The caller, the target profile and the session token.

        Raises:
            UserNotFoundException: If the caller's account no longer exists
                (HTTP 404).
            ProfileNotFoundException: If the target does not exist or is
                deleted meanwhile (HTTP 404).
            ProfileOwnershipViolation: If the caller does not own the target
                (HTTP 403).
            ParentalPinRequiredError: If the gate needs an unlock this session
                cannot spend, or the target's limit keeps changing under the
                switch (HTTP 403).
            NoActiveSessionError: If no session has the token (HTTP 401).
        """
        caller_id = UserId(input_dto.user_id)
        target_id = ProfileId(input_dto.target_profile_id)
        token = input_dto.session_token

        async with self._uow_factory() as uow:
            await lock_account(uow, caller_id)
            unlock_spent = False
            for _attempt in range(2):
                profile = await uow.profiles.find_by_id(target_id)
                if profile is None:
                    raise ProfileNotFoundException.for_resource(
                        resource_type="Profile",
                        resource_id=input_dto.target_profile_id,
                    )

                if profile.user_id != caller_id:
                    raise ProfileOwnershipViolation(
                        message="You do not own this profile",
                    )

                session = await read_gate_session(uow, caller_id, token)
                if (
                    not unlock_spent
                    and session.pin_configured
                    and ParentalGate.exceeds(profile.maturity_limit, session.limit)
                ):
                    await spend_unlock(uow, session, now=self._clock())
                    unlock_spent = True

                if await uow.access_tokens.update_current_profile(
                    token,
                    target_id,
                    expected_limit=profile.maturity_limit,
                ):
                    return
                if await uow.access_tokens.get_by_token(token) is None:
                    raise NoActiveSessionError(
                        message="No active session for the provided token",
                    )

            raise ParentalPinRequiredError(
                message="The profile changed during the switch; try again",
            )


__all__ = ["SwitchProfileUseCase"]
