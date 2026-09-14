"""UnlockParentalUseCase — open a device's parental unlock window with the PIN."""

from collections.abc import Callable
from datetime import UTC, datetime

from src.modules.identity.application.dtos.identity_dtos import UnlockParentalInput
from src.modules.identity.application.errors import NoActiveSessionError, UserNotFoundException
from src.modules.identity.application.ports import PasswordHasherPort
from src.modules.identity.application.unit_of_work import IdentityUnitOfWorkFactory
from src.modules.identity.domain.errors import (
    ParentalPinInvalidError,
    ParentalPinLockedError,
    ParentalPinNotConfiguredError,
)
from src.modules.identity.domain.services.parental_gate import UNLOCK_WINDOW, LockoutPolicy
from src.modules.identity.domain.value_objects.parental_pin import ParentalPin
from src.shared_kernel.value_objects.user_id import UserId


def _utc_now() -> datetime:
    return datetime.now(UTC)


class UnlockParentalUseCase:
    """Check the parental PIN on one device and, if right, unlock it for five minutes.

    Attempts, locks and the unlock window belong to the session token, so a
    child locking the tablet never locks the parent's TV (ADR-035, Amendment
    7 D4). Five wrong PINs lock the device for five minutes, doubling up to a
    day; a correct PIN clears the attempts and ends a lock in force but does
    not lower the ladder.

    Nothing reads the window yet: the admin and profile gates that consume
    it arrive in later changes.

    The steps are ordered so that neither a rollback nor concurrency can
    hand attempts back:

    1. The PIN format is checked first, so a malformed value costs neither an
       attempt nor a hash verification.
    2. The session and the account's PIN hash are read in a short
       transaction.
    3. The attempt is reserved in its own transaction, which commits before
       anything is raised: raising inside it would roll the count back. The
       reservation is one conditional write, so concurrent requests cannot
       all pass a check made before the count.
    4. The PIN is verified outside any transaction — the hash check is slow
       and synchronous — and never while a lock is in force.
    5. A correct PIN is recorded in a last short transaction; a wrong one is
       raised with nothing left to write.
    """

    def __init__(
        self,
        uow_factory: IdentityUnitOfWorkFactory,
        password_hasher: PasswordHasherPort,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._uow_factory = uow_factory
        self._password_hasher = password_hasher
        self._clock = clock
        self._policy = LockoutPolicy()

    async def execute(self, input_dto: UnlockParentalInput) -> None:
        """Verify the PIN for the caller's session and open its unlock window.

        Args:
            input_dto: The caller's user id, session token and PIN.

        Raises:
            DomainValidationException: If the PIN is not exactly six ASCII
                digits (HTTP 422). No attempt is counted; the value is not
                echoed.
            NoActiveSessionError: If no session has the token.
            UserNotFoundException: If the account no longer exists.
            ParentalPinNotConfiguredError: If the account has no PIN (HTTP 409).
            ParentalPinLockedError: If the session is locked — the PIN is not
                checked — or this wrong PIN started the lock (HTTP 403, with
                ``retry_after_seconds``).
            ParentalPinInvalidError: If the PIN is wrong (HTTP 403). The
                attempt stays counted.
        """
        user_id = UserId(input_dto.user_id)
        pin = ParentalPin(input_dto.pin)
        token = input_dto.session_token

        async with self._uow_factory() as uow:
            state = await uow.access_tokens.get_parental_state(token)
            user = await uow.users.find_by_id(user_id)
        if state is None or state.user_id != user_id:
            raise NoActiveSessionError(message="No active session for the provided token")
        if user is None:
            raise UserNotFoundException.for_resource("User", input_dto.user_id)
        if user.parental_pin_hash is None:
            raise ParentalPinNotConfiguredError(message="The account has no parental PIN")

        now = self._clock()
        async with self._uow_factory() as uow:
            reservation = await uow.access_tokens.reserve_pin_attempt(
                token, now=now, policy=self._policy
            )
        if not reservation.granted:
            if reservation.locked_until is None:
                raise NoActiveSessionError(message="No active session for the provided token")
            raise ParentalPinLockedError.until(reservation.locked_until, now=now)

        if not self._password_hasher.verify(pin.value, user.parental_pin_hash):
            if reservation.locked_until is not None:
                raise ParentalPinLockedError.until(reservation.locked_until, now=now)
            raise ParentalPinInvalidError(message="The parental PIN is incorrect")

        async with self._uow_factory() as uow:
            await uow.access_tokens.record_pin_success(
                token, now=now, unlock_until=now + UNLOCK_WINDOW
            )


__all__ = ["UnlockParentalUseCase"]
