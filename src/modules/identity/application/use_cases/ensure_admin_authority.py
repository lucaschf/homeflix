"""EnsureAdminAuthorityUseCase — refuse a request the session's admin authority does not cover."""

from src.building_blocks.application.errors import ForbiddenOperationException
from src.modules.identity.application.dtos.identity_dtos import (
    AdminAccessLevel,
    GetAdminAccessInput,
)
from src.modules.identity.application.use_cases.get_admin_access import GetAdminAccessUseCase
from src.modules.identity.domain.errors import ParentalPinRequiredError


class EnsureAdminAuthorityUseCase:
    """Let an admin request through only when the session holds admin authority.

    Raises from the same decision :class:`GetAdminAccessUseCase` reports, so
    the admin route guard and ``/users/me`` never disagree. A suspension is
    403 ``PARENTAL_PIN_REQUIRED``, never 401: the web client reads any 401 as
    an expired session and signs the user out.
    """

    def __init__(self, get_admin_access: GetAdminAccessUseCase) -> None:
        self._get_admin_access = get_admin_access

    async def execute(self, input_dto: GetAdminAccessInput) -> None:
        """Return when the session may use admin authority for this request.

        Args:
            input_dto: The authenticated account's id, role and PIN presence,
                the session token and whether the request changes state.

        Raises:
            ForbiddenOperationException: If the account does not hold the
                admin role (HTTP 403 ``ADMIN_REQUIRED``).
            ParentalPinRequiredError: If the parental gate suspends the
                session's admin authority (HTTP 403).
        """
        access = await self._get_admin_access.execute(input_dto)
        if access is AdminAccessLevel.GRANTED:
            return
        if access is AdminAccessLevel.NONE:
            raise ForbiddenOperationException(
                message="Admin role required",
                message_code="ADMIN_REQUIRED",
                required_permission="admin",
            )
        raise ParentalPinRequiredError(
            message="Admin authority on this device needs the parental PIN",
        )


__all__ = ["EnsureAdminAuthorityUseCase"]
