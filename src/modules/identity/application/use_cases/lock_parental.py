"""LockParentalUseCase — close a device's parental unlock window."""

from src.modules.identity.application.dtos.identity_dtos import LockParentalInput
from src.modules.identity.application.unit_of_work import IdentityUnitOfWorkFactory


class LockParentalUseCase:
    """Close the unlock window of the caller's session before it runs out.

    Only the window closes: the attempt counter, a lock in force and the
    lockout ladder stay as they are, so locking is never a way to earn more
    PIN attempts (ADR-035, Amendment 7 D4). Closing a session with no open
    window succeeds.
    """

    def __init__(self, uow_factory: IdentityUnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def execute(self, input_dto: LockParentalInput) -> None:
        """Close the unlock window of the session.

        Args:
            input_dto: The caller's session token.
        """
        async with self._uow_factory() as uow:
            await uow.access_tokens.clear_unlock(input_dto.session_token)


__all__ = ["LockParentalUseCase"]
