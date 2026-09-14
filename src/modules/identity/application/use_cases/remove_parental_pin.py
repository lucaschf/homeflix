"""RemoveParentalPinUseCase — clear the household parental PIN."""

from src.modules.identity.application.dtos.identity_dtos import RemoveParentalPinInput
from src.modules.identity.application.errors import UserNotFoundException
from src.modules.identity.application.ports import PasswordHasherPort
from src.modules.identity.application.unit_of_work import IdentityUnitOfWorkFactory
from src.modules.identity.application.use_cases._account_password import (
    ensure_account_password,
)
from src.modules.identity.domain.errors import ParentalPinInUseError
from src.shared_kernel.value_objects.user_id import UserId


class RemoveParentalPinUseCase:
    """Remove the account's parental PIN.

    Requires the account password, like setting it (ADR-035, Amendment 7
    D3); this is also the way out of a forgotten PIN. Removing when no PIN
    is configured succeeds and leaves the account without one. While any
    live profile of the account still has a maturity limit the PIN cannot
    be removed (D2): no limit may be left without a PIN to protect it.

    The password check is slow and synchronous, so it runs between two
    short transactions, never inside one: the first reads the user, the
    second clears only the PIN hash. Saving the entity read before the
    check would write it back stale, undoing a demotion or a soft delete
    committed meanwhile; the narrow write cannot, and a user deleted
    meanwhile answers "not found".

    **Atomicity.** Checking the profiles and then clearing the hash would let
    a limit written in between survive without a PIN. The check is part of
    the write instead: one conditional statement
    (``clear_unused_parental_pin_hash``) clears the hash only while no live
    profile has a limit. When it does not take effect the user is read
    again in the same transaction: gone → ``UserNotFoundException``;
    otherwise a live profile has a limit → ``ParentalPinInUseError``.

    The write transaction opens with the account lock
    (``UserRepository.lock_for_parental_change``) that every gated profile
    operation opens with, so the PIN never disappears between the reads of
    one of them and its write; an account deleted meanwhile answers "not
    found" there.
    """

    def __init__(
        self,
        uow_factory: IdentityUnitOfWorkFactory,
        password_hasher: PasswordHasherPort,
    ) -> None:
        self._uow_factory = uow_factory
        self._password_hasher = password_hasher

    async def execute(self, input_dto: RemoveParentalPinInput) -> None:
        """Confirm the account password and clear the stored PIN hash.

        Args:
            input_dto: The caller's user id and account password.

        Raises:
            UserNotFoundException: If the account no longer exists, including
                when it is deleted while the password is being checked.
            AccountPasswordInvalidError: If the account password is wrong
                (HTTP 403). Nothing is written.
            ParentalPinInUseError: If a live profile of the account has a
                maturity limit (HTTP 409). Nothing is written.
        """
        user_id = UserId(input_dto.user_id)

        async with self._uow_factory() as uow:
            user = await uow.users.find_by_id(user_id)
        if user is None:
            raise UserNotFoundException.for_resource("User", input_dto.user_id)

        ensure_account_password(user, input_dto.current_password, self._password_hasher)

        async with self._uow_factory() as uow:
            if not await uow.users.lock_for_parental_change(user_id):
                raise UserNotFoundException.for_resource("User", input_dto.user_id)
            if await uow.users.clear_unused_parental_pin_hash(user_id):
                return
            # The statement left out only a missing user or a limited profile.
            if await uow.users.find_by_id(user_id) is None:
                raise UserNotFoundException.for_resource("User", input_dto.user_id)
            raise ParentalPinInUseError(
                message="Remove every profile's maturity limit before the parental PIN",
            )


__all__ = ["RemoveParentalPinUseCase"]
