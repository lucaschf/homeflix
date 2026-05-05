"""Profile CRUD + switch + avatar routes."""

from dataclasses import asdict
from pathlib import Path
from typing import Any

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse

from src.building_blocks.presentation import api_list, api_single
from src.config.containers import ApplicationContainer
from src.config.settings import get_settings
from src.modules.identity.application.dtos.identity_dtos import (
    CreateProfileInput,
    DeleteProfileAvatarInput,
    DeleteProfileInput,
    ListProfilesForUserInput,
    SwitchProfileInput,
    UpdateProfileInput,
    UploadProfileAvatarInput,
)
from src.modules.identity.application.ports import (
    AvatarTooLargeError,
    InvalidAvatarImageError,
)
from src.modules.identity.application.use_cases.create_profile import (
    CreateProfileUseCase,
)
from src.modules.identity.application.use_cases.delete_profile import (
    DeleteProfileUseCase,
)
from src.modules.identity.application.use_cases.delete_profile_avatar import (
    DeleteProfileAvatarUseCase,
)
from src.modules.identity.application.use_cases.list_profiles_for_user import (
    ListProfilesForUserUseCase,
)
from src.modules.identity.application.use_cases.switch_profile import (
    SwitchProfileUseCase,
)
from src.modules.identity.application.use_cases.update_profile import (
    UpdateProfileUseCase,
)
from src.modules.identity.application.use_cases.upload_profile_avatar import (
    UploadProfileAvatarUseCase,
)
from src.modules.identity.infrastructure.auth import (
    current_active_user,
    get_session_token,
)
from src.modules.identity.infrastructure.persistence.models.user_model import UserModel
from src.modules.identity.presentation.schemas.profile_schemas import (
    CreateProfileRequest,
    UpdateProfileRequest,
)

router = APIRouter(prefix="/api/v1/profiles", tags=["Profiles"])


@router.get("")  # type: ignore[misc]
@inject  # type: ignore[misc]
async def list_profiles(
    user: UserModel = Depends(current_active_user),
    use_case: ListProfilesForUserUseCase = Depends(
        Provide[ApplicationContainer.identity.list_profiles_for_user],
    ),
) -> dict[str, Any]:
    """List the authenticated user's profiles."""
    result = await use_case.execute(
        ListProfilesForUserInput(user_id=user.external_id),
    )
    return api_list([asdict(p) for p in result])


@router.post("", status_code=201)  # type: ignore[misc]
@inject  # type: ignore[misc]
async def create_profile(
    body: CreateProfileRequest,
    user: UserModel = Depends(current_active_user),
    use_case: CreateProfileUseCase = Depends(
        Provide[ApplicationContainer.identity.create_profile],
    ),
) -> dict[str, Any]:
    """Create a new profile owned by the authenticated user."""
    result = await use_case.execute(
        CreateProfileInput(
            user_id=user.external_id,
            name=body.name,
            is_kids=body.is_kids,
            avatar_url=body.avatar_url,
            allowed_library_ids=body.allowed_library_ids,
        ),
    )
    return api_single("profile", asdict(result))


@router.put("/{profile_id}")  # type: ignore[misc]
@inject  # type: ignore[misc]
async def update_profile(
    profile_id: str,
    body: UpdateProfileRequest,
    user: UserModel = Depends(current_active_user),
    use_case: UpdateProfileUseCase = Depends(
        Provide[ApplicationContainer.identity.update_profile],
    ),
) -> dict[str, Any]:
    """Partial update; only supplied fields touch the entity.

    Ownership is enforced inside the use case — a caller acting on
    someone else's profile gets HTTP 403 from
    ``ProfileOwnershipViolation``.
    """
    result = await use_case.execute(
        UpdateProfileInput(
            user_id=user.external_id,
            profile_id=profile_id,
            name=body.name,
            is_kids=body.is_kids,
            avatar_url=body.avatar_url,
            allowed_library_ids=body.allowed_library_ids,
        ),
    )
    return api_single("profile", asdict(result))


@router.delete("/{profile_id}", status_code=204)  # type: ignore[misc]
@inject  # type: ignore[misc]
async def delete_profile(
    profile_id: str,
    user: UserModel = Depends(current_active_user),
    use_case: DeleteProfileUseCase = Depends(
        Provide[ApplicationContainer.identity.delete_profile],
    ),
) -> None:
    """Soft-delete a profile.

    Returns 403 if the caller does not own the profile and 409 if
    deletion would leave the user without any active profile.
    """
    await use_case.execute(
        DeleteProfileInput(user_id=user.external_id, profile_id=profile_id),
    )


@router.post("/{profile_id}/switch", status_code=204)  # type: ignore[misc]
@inject  # type: ignore[misc]
async def switch_profile(
    profile_id: str,
    user: UserModel = Depends(current_active_user),
    token: str = Depends(get_session_token),
    use_case: SwitchProfileUseCase = Depends(
        Provide[ApplicationContainer.identity.switch_profile],
    ),
) -> None:
    """Set the target profile as the active one in the caller's session.

    The session token (read by ``get_session_token`` from the cookie)
    is passed to the use case so it updates the matching
    ``access_tokens`` row. The cookie itself is not re-emitted —
    multi-device sessions can each carry their own active profile
    per ADR-011.
    """
    await use_case.execute(
        SwitchProfileInput(
            user_id=user.external_id,
            target_profile_id=profile_id,
            session_token=token,
        ),
    )


@router.post("/{profile_id}/avatar")  # type: ignore[misc]
@inject  # type: ignore[misc]
async def upload_profile_avatar(
    profile_id: str,
    file: UploadFile = File(...),
    user: UserModel = Depends(current_active_user),
    use_case: UploadProfileAvatarUseCase = Depends(
        Provide[ApplicationContainer.identity.upload_profile_avatar],
    ),
) -> dict[str, Any]:
    """Upload a new avatar image for the given profile.

    Multipart upload accepting JPEG / PNG / WebP. The server
    validates the bytes (Pillow decode), centre-crops to a square
    and persists as WebP. Bad MIME → 415; oversized payload → 413;
    cross-user upload → 403; unknown profile → 404.
    """
    content = await file.read()
    try:
        result = await use_case.execute(
            UploadProfileAvatarInput(
                user_id=user.external_id,
                profile_id=profile_id,
                content=content,
                declared_mime_type=file.content_type or "application/octet-stream",
            ),
        )
    except AvatarTooLargeError as exc:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=str(exc),
        ) from exc
    except InvalidAvatarImageError as exc:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=str(exc),
        ) from exc
    return api_single("profile", asdict(result))


@router.delete("/{profile_id}/avatar")  # type: ignore[misc]
@inject  # type: ignore[misc]
async def delete_profile_avatar(
    profile_id: str,
    user: UserModel = Depends(current_active_user),
    use_case: DeleteProfileAvatarUseCase = Depends(
        Provide[ApplicationContainer.identity.delete_profile_avatar],
    ),
) -> dict[str, Any]:
    """Clear the profile's avatar (sets ``avatar_url`` null + deletes file).

    Idempotent — calling on a profile that has no avatar succeeds
    and returns the (still-empty) profile.
    """
    result = await use_case.execute(
        DeleteProfileAvatarInput(user_id=user.external_id, profile_id=profile_id),
    )
    return api_single("profile", asdict(result))


@router.get("/{profile_id}/avatar")  # type: ignore[misc]
async def get_profile_avatar(
    profile_id: str,
    _user: UserModel = Depends(current_active_user),
) -> FileResponse:
    """Serve the persisted avatar WebP for ``profile_id``.

    Auth-gated (``current_active_user``) but **not** ownership-gated:
    any authenticated household member needs to be able to render
    siblings' avatars in the picker / AccountMenu. The file path is
    deterministic from the profile id, so resolving it here doesn't
    require a database round-trip — kept lean because the picker
    fires one of these per profile on every render.
    """
    settings = get_settings()
    target = (
        Path(settings.thumbnails_directory) / settings.avatar_storage_subdir / f"{profile_id}.webp"
    )
    if not target.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="avatar not found",
        )
    return FileResponse(str(target), media_type="image/webp")


__all__ = ["router"]
