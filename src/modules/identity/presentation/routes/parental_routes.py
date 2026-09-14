"""Parental-control routes for the identity bounded context (ADR-035).

The household parental PIN belongs to the account. These routes only
store and remove it; nothing checks the PIN yet. Every failure on this
surface is a 4xx other than 401 — a wrong account password is 403 — so
the frontend never mistakes it for an expired session.
"""

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends

from src.config.containers import ApplicationContainer
from src.modules.identity.application.dtos.identity_dtos import (
    RemoveParentalPinInput,
    SetParentalPinInput,
)
from src.modules.identity.application.use_cases.remove_parental_pin import (
    RemoveParentalPinUseCase,
)
from src.modules.identity.application.use_cases.set_parental_pin import (
    SetParentalPinUseCase,
)
from src.modules.identity.infrastructure.auth import current_active_user
from src.modules.identity.infrastructure.persistence.models.user_model import UserModel
from src.modules.identity.presentation.schemas.parental_schemas import (
    RemoveParentalPinRequest,
    SetParentalPinRequest,
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
    is 403 ``ACCOUNT_PASSWORD_INVALID``. A POST rather than a DELETE so the
    password travels in a request body.
    """
    await use_case.execute(
        RemoveParentalPinInput(
            user_id=user.external_id,
            current_password=body.current_password.get_secret_value(),
        ),
    )


__all__ = ["router"]
