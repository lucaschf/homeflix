"""GetAdminAccessUseCase — the administrator authority a session holds right now."""

from collections.abc import Callable
from datetime import UTC, datetime

from src.modules.identity.application.dtos.identity_dtos import (
    AdminAccessLevel,
    GetAdminAccessInput,
)
from src.modules.identity.application.unit_of_work import IdentityUnitOfWorkFactory
from src.modules.identity.domain.services.parental_gate import AdminAccess, ParentalGate
from src.modules.identity.domain.value_objects.user_role import UserRole
from src.shared_kernel.value_objects.user_id import UserId


def _utc_now() -> datetime:
    return datetime.now(UTC)


class GetAdminAccessUseCase:
    """Decide whether a session may use administrator authority (ADR-035).

    Once an account has a parental PIN, admin authority follows the
    session: the selected profile and the device's unlock window decide it,
    as the Amendment 7 matrix in :meth:`ParentalGate.admin_access` states.
    An account without a PIN keeps the plain role, and costs no query.

    With a PIN, the decision reads the session's parental state and the
    account's live profiles in one statement
    (``AccessTokenRepository.get_parental_snapshot``). Read in two, a
    widening committed between them — which also detaches this session from
    the widened profile — would pair the session still on that profile with
    the profile already unrestricted, and grant a read no request order
    grants; admin requests take no account lock, so the single snapshot is
    what keeps them consistent without serialising them. A selected profile
    missing from that list was soft-deleted and counts as ``AgeRating(0)``.
    The unlock window is read, never spent (Amendment 7 D9).
    """

    def __init__(
        self,
        uow_factory: IdentityUnitOfWorkFactory,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    async def execute(self, input_dto: GetAdminAccessInput) -> AdminAccessLevel:
        """Return the admin authority of the caller's session.

        Args:
            input_dto: The authenticated account's id, role and PIN presence,
                the session token and whether the request changes state.

        Returns:
            ``NONE`` without the admin role; ``GRANTED`` without a PIN; with
            one, ``GRANTED`` or ``SUSPENDED`` by the parental gate. A token
            that no longer matches a session of the account is
            ``SUSPENDED``: nothing proves its profile or unlock.
        """
        if input_dto.role is not UserRole.ADMIN:
            return AdminAccessLevel.NONE
        if not input_dto.parental_pin_configured:
            return AdminAccessLevel.GRANTED

        user_id = UserId(input_dto.user_id)
        async with self._uow_factory() as uow:
            snapshot = await uow.access_tokens.get_parental_snapshot(input_dto.session_token)
        if snapshot is None or snapshot.state.user_id != user_id:
            return AdminAccessLevel.SUSPENDED

        state = snapshot.state
        access = ParentalGate.admin_access(
            pin_configured=input_dto.parental_pin_configured,
            active_profile_id=state.current_profile_id,
            account_profiles=snapshot.account_profiles,
            unlock_until=state.unlock_until,
            now=self._clock(),
            is_write=input_dto.is_write,
        )
        if access is AdminAccess.GRANTED:
            return AdminAccessLevel.GRANTED
        return AdminAccessLevel.SUSPENDED


__all__ = ["GetAdminAccessUseCase"]
