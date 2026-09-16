"""Member-facing reads over the runtime settings.

The admin surface (``/api/v1/admin/settings``) exposes every bucket in
full to operators. This router is the narrow counterpart: the few
operator-tunable values a *member's* client must know to behave
correctly, each projected down to the fields it acts on. Filesystem
paths, provider credentials and scheduler internals never appear here.
"""

from dataclasses import asdict
from typing import Any

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends

from src.building_blocks.presentation import api_single
from src.config.containers import ApplicationContainer
from src.modules.identity.presentation.public import AuthenticatedUser, authenticated_user
from src.modules.settings.application.use_cases import GetAvatarLimitsUseCase

router = APIRouter(prefix="/api/v1/settings", tags=["Settings"])


@router.get("/avatar")
@inject
async def get_avatar_limits(
    _user: AuthenticatedUser = Depends(authenticated_user),
    use_case: GetAvatarLimitsUseCase = Depends(
        Provide[ApplicationContainer.settings.get_avatar_limits],
    ),
) -> dict[str, Any]:
    """Return the limits an avatar upload is subject to right now.

    Authenticated, not admin-gated: the cap is operator-tunable via
    ``PATCH /api/v1/admin/settings/avatar`` (1 to 20 MB), so a member's
    client that hard-codes a value either rejects a file the server would
    accept or lets one through for the server to refuse with 413. Reading
    it makes the client's check agree with the server's.

    Only ``max_size_bytes``, ``max_size_mb`` and ``size_pixels`` are
    exposed — ``storage_subdir`` is a server path with nothing for a
    client to do and stays on the admin surface.
    """
    limits = await use_case.execute()
    return api_single("avatar_limits", asdict(limits))


__all__ = ["router"]
