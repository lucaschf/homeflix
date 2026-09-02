"""Playback preferences REST API routes."""

from dataclasses import asdict
from typing import Any

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends

from src.building_blocks.presentation import api_single
from src.config.containers import ApplicationContainer
from src.modules.preferences.application.dtos.preferences_dtos import (
    GetPreferencesInput,
    UpdatePreferencesInput,
)
from src.modules.preferences.application.use_cases.get_preferences import (
    GetPreferencesUseCase,
)
from src.modules.preferences.application.use_cases.update_preferences import (
    UpdatePreferencesUseCase,
)
from src.modules.preferences.presentation.dependencies import resolve_profile_id
from src.modules.preferences.presentation.schemas.preferences_schemas import (
    UpdatePreferencesRequest,
)

router = APIRouter(prefix="/api/v1/preferences", tags=["Preferences"])


@router.get("")
@inject
async def get_preferences(
    profile_id: str = Depends(resolve_profile_id),
    use_case: GetPreferencesUseCase = Depends(
        Provide[ApplicationContainer.preferences.get_preferences],
    ),
) -> dict[str, Any]:
    """Return the current profile's playback preferences."""
    result = await use_case.execute(GetPreferencesInput(profile_id=profile_id))
    return api_single("preferences", asdict(result))


@router.put("")
@inject
async def update_preferences(
    body: UpdatePreferencesRequest,
    profile_id: str = Depends(resolve_profile_id),
    use_case: UpdatePreferencesUseCase = Depends(
        Provide[ApplicationContainer.preferences.update_preferences],
    ),
) -> dict[str, Any]:
    """Partially update (or create) playback preferences."""
    result = await use_case.execute(
        UpdatePreferencesInput(
            profile_id=profile_id,
            audio_lang=body.audio_lang,
            subtitle_lang=body.subtitle_lang,
            subtitle_mode=body.subtitle_mode,
            default_quality=body.default_quality,
            speed=body.speed,
            subtitle_appearance=(
                body.subtitle_appearance.model_dump(exclude_none=True)
                if body.subtitle_appearance is not None
                else None
            ),
            intro_skip_mode=body.intro_skip_mode,
            credits_skip_mode=body.credits_skip_mode,
        )
    )
    return api_single("preferences", asdict(result))


__all__ = ["router"]
