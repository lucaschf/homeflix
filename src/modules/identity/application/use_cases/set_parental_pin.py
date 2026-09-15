"""SetParentalPinUseCase — set or replace the household parental PIN."""

from src.modules.identity.application.dtos.identity_dtos import SetParentalPinInput
from src.modules.identity.application.errors import UserNotFoundException
from src.modules.identity.application.ports import PasswordHasherPort
from src.modules.identity.application.unit_of_work import IdentityUnitOfWorkFactory
from src.modules.identity.application.use_cases._account_password import (
    ensure_account_password,
)
from src.modules.identity.domain.value_objects.parental_pin import ParentalPin
from src.shared_kernel.value_objects.user_id import UserId


class SetParentalPinUseCase:
    """Store a hash of the account's parental PIN, replacing any previous one.

    The PIN belongs to the account (the household), not to a profile, and
    setting or replacing it requires the account password (ADR-035,
    Amendment 7 D3). Only the hash is stored. Nothing checks the PIN yet:
    unlocking and the gates that consume it arrive in later changes.

    The PIN format is checked before the password, so a malformed request
    fails without spending a password verification.

    The password check and the PIN hashing are slow and synchronous, so
    they run between two short transactions, never inside one (as in
    ``CreateAdminUserUseCase``): the first reads the user, the second
    writes only the PIN hash. Saving the entity read before the check
    would write it back stale, undoing a demotion or a soft delete
    committed meanwhile; the narrow write cannot, and a user deleted
    meanwhile answers "not found".

    The write transaction opens with the account lock
    (``UserRepository.lock_for_parental_change``) that every gated profile
    operation opens with, so a new PIN never lands between the reads of one
    of them and its write (ADR-035, Amendment 7).
    """

    def __init__(
        self,
        uow_factory: IdentityUnitOfWorkFactory,
        password_hasher: PasswordHasherPort,
    ) -> None:
        self._uow_factory = uow_factory
        self._password_hasher = password_hasher

    async def execute(self, input_dto: SetParentalPinInput) -> None:
        """Confirm the account password and store the new PIN's hash.

        Args:
            input_dto: The caller's user id, account password and new PIN.

        Raises:
            DomainValidationException: If the PIN is not exactly six ASCII
                digits (HTTP 422). The value is not echoed.
            UserNotFoundException: If the account no longer exists, including
                when it is deleted while the password is being checked.
            AccountPasswordInvalidError: If the account password is wrong
                (HTTP 403). Nothing is written.
        """
        user_id = UserId(input_dto.user_id)
        pin = ParentalPin(input_dto.pin)

        async with self._uow_factory() as uow:
            user = await uow.users.find_by_id(user_id)
        if user is None:
            raise UserNotFoundException.for_resource("User", input_dto.user_id)

        ensure_account_password(user, input_dto.current_password, self._password_hasher)
        hashed = self._password_hasher.hash(pin.value)

        async with self._uow_factory() as uow:
            if not await uow.users.lock_for_parental_change(user_id):
                raise UserNotFoundException.for_resource("User", input_dto.user_id)
            stored = await uow.users.set_parental_pin_hash(user_id, hashed)
        if not stored:
            raise UserNotFoundException.for_resource("User", input_dto.user_id)


__all__ = ["SetParentalPinUseCase"]
