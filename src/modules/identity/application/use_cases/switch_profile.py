"""SwitchProfileUseCase."""

from src.modules.identity.application.dtos.identity_dtos import SwitchProfileInput
from src.modules.identity.application.errors import (
    NoActiveSessionError,
    ProfileNotFoundException,
    ProfileOwnershipViolation,
)
from src.modules.identity.application.unit_of_work import IdentityUnitOfWorkFactory
from src.shared_kernel.value_objects.profile_id import ProfileId
from src.shared_kernel.value_objects.user_id import UserId


class SwitchProfileUseCase:
    """Change the active profile carried by the caller's session.

    Persists the chosen profile in ``access_tokens.current_profile_id``
    so subsequent requests resolve to it via ``get_current_profile``.
    The cookie itself is not re-emitted — the row update is the only
    side effect, which means multi-device sessions can each carry
    their own active profile (per ADR-011).

    Enforces:

    - **Profile exists**: missing target → :class:`ProfileNotFoundException`
      (HTTP 404).
    - **Ownership**: target must belong to the caller →
      :class:`ProfileOwnershipViolation` (HTTP 403).
    - **Session exists**: the caller's session row must be present —
      a missing token means the cookie was tampered with or already
      revoked → :class:`NoActiveSessionError` (HTTP 401).
    """

    def __init__(self, uow_factory: IdentityUnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def execute(self, input_dto: SwitchProfileInput) -> None:
        """Persist the target profile as the active one in the caller's session."""
        caller_id = UserId(input_dto.user_id)
        target_id = ProfileId(input_dto.target_profile_id)

        async with self._uow_factory() as uow:
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

            updated = await uow.access_tokens.update_current_profile(
                input_dto.session_token,
                target_id,
            )
            if not updated:
                raise NoActiveSessionError(
                    message="No active session for the provided token",
                )


__all__ = ["SwitchProfileUseCase"]
