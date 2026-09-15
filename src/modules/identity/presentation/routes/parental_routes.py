"""Parental-control routes for the identity bounded context (ADR-035).

The household parental PIN belongs to the account; attempts, lockouts
and the unlock window belong to the session, i.e. to the device. These
routes store and remove the PIN and open or close a device's unlock
window; no gate reads that window yet. Every failure on this surface is
a 4xx other than 401 — a wrong account password or PIN is 403 — so the
frontend never mistakes it for an expired session.
"""

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends

from src.config.containers import ApplicationContainer
from src.modules.identity.application.dtos.identity_dtos import (
    LockParentalInput,
    RemoveParentalPinInput,
    SetParentalPinInput,
    UnlockParentalInput,
)
from src.modules.identity.application.use_cases.lock_parental import LockParentalUseCase
from src.modules.identity.application.use_cases.remove_parental_pin import (
    RemoveParentalPinUseCase,
)
from src.modules.identity.application.use_cases.set_parental_pin import (
    SetParentalPinUseCase,
)
from src.modules.identity.application.use_cases.unlock_parental import (
    UnlockParentalUseCase,
)
from src.modules.identity.infrastructure.auth import current_active_user, get_session_token
from src.modules.identity.infrastructure.persistence.models.user_model import UserModel
from src.modules.identity.presentation.schemas.parental_schemas import (
    RemoveParentalPinRequest,
    SetParentalPinRequest,
    UnlockParentalRequest,
)

router = APIRouter(prefix="/api/v1/parental", tags=["Parental controls"])


@router.put("/pin", status_code=204)
@inject
async def set_parental_pin(
    body: SetParentalPinRequest,
    user: UserModel = Depends(current_active_user),
    use_case: SetParentalPinUseCase = Depends(
        Provide[ApplicationContainer.identity.set_parental_pin],
    ),
) -> None:
    """Set or replace the account's parental PIN.

    Returns 204. A PIN that is not exactly six digits is 422 and a wrong
    account password is 403 ``ACCOUNT_PASSWORD_INVALID``; neither response
    echoes the submitted values.
    """
    await use_case.execute(
        SetParentalPinInput(
            user_id=user.external_id,
            current_password=body.current_password.get_secret_value(),
            pin=body.pin.get_secret_value(),
        ),
    )


@router.post("/pin/remove", status_code=204)
@inject
async def remove_parental_pin(
    body: RemoveParentalPinRequest,
    user: UserModel = Depends(current_active_user),
    use_case: RemoveParentalPinUseCase = Depends(
        Provide[ApplicationContainer.identity.remove_parental_pin],
    ),
) -> None:
    """Remove the account's parental PIN.

    Returns 204, also when no PIN was configured. A wrong account password
    is 403 ``ACCOUNT_PASSWORD_INVALID``, and a live profile with a maturity
    limit is 409 ``PARENTAL_PIN_IN_USE``. A POST rather than a DELETE so the
    password travels in a request body.
    """
    await use_case.execute(
        RemoveParentalPinInput(
            user_id=user.external_id,
            current_password=body.current_password.get_secret_value(),
        ),
    )


@router.post("/unlock", status_code=204)
@inject
async def unlock_parental(
    body: UnlockParentalRequest,
    user: UserModel = Depends(current_active_user),
    token: str = Depends(get_session_token),
    use_case: UnlockParentalUseCase = Depends(
        Provide[ApplicationContainer.identity.unlock_parental],
    ),
) -> None:
    """Unlock this device for five minutes with the parental PIN.

    Returns 204. A wrong PIN is 403 ``PARENTAL_PIN_INVALID``; the attempt
    that locks the device, and every attempt while it is locked, is 403
    ``PARENTAL_PIN_LOCKED`` with ``details[0].metadata.retry_after_seconds``.
    An account without a PIN is 409 ``PARENTAL_PIN_NOT_CONFIGURED`` and a
    PIN that is not six digits is 422, neither echoing the value.
    """
    await use_case.execute(
        UnlockParentalInput(
            user_id=user.external_id,
            session_token=token,
            pin=body.pin.get_secret_value(),
        ),
    )


@router.delete("/unlock", status_code=204)
@inject
async def lock_parental(
    _user: UserModel = Depends(current_active_user),
    token: str = Depends(get_session_token),
    use_case: LockParentalUseCase = Depends(
        Provide[ApplicationContainer.identity.lock_parental],
    ),
) -> None:
    """Close this device's unlock window before it runs out.

    Returns 204, also when no window was open. Only the window closes: the
    device's PIN attempts and any lock are unchanged.
    """
    await use_case.execute(LockParentalInput(session_token=token))


__all__ = ["router"]
