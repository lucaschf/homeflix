"""Playback preferences REST API routes."""

from dataclasses import asdict
from typing import Any

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends

from src.building_blocks.presentation import api_single
from src.config.containers import ApplicationContainer
from src.modules.preferences.application.dtos.preferences_dtos import (
    UpdatePreferencesInput,
)
from src.modules.preferences.application.use_cases.get_preferences import (
    GetPreferencesUseCase,
)
from src.modules.preferences.application.use_cases.update_preferences import (
    UpdatePreferencesUseCase,
)
from src.modules.preferences.presentation.schemas.preferences_schemas import (
    UpdatePreferencesRequest,
)

router = APIRouter(prefix="/api/v1/preferences", tags=["Preferences"])


@router.get("")  # type: ignore[misc]
@inject  # type: ignore[misc]
async def get_preferences(
    use_case: GetPreferencesUseCase = Depends(
        Provide[ApplicationContainer.preferences.get_preferences],
    ),
) -> dict[str, Any]:
    """Return the current user's playback preferences."""
    result = await use_case.execute()
    return api_single("preferences", asdict(result))


@router.put("")  # type: ignore[misc]
@inject  # type: ignore[misc]
async def update_preferences(
    body: UpdatePreferencesRequest,
    use_case: UpdatePreferencesUseCase = Depends(
        Provide[ApplicationContainer.preferences.update_preferences],
    ),
) -> dict[str, Any]:
    """Partially update (or create) playback preferences."""
    result = await use_case.execute(
        UpdatePreferencesInput(
            audio_lang=body.audio_lang,
            subtitle_lang=body.subtitle_lang,
            subtitle_mode=body.subtitle_mode,
            default_quality=body.default_quality,
            speed=body.speed,
        )
    )
    return api_single("preferences", asdict(result))


__all__ = ["router"]
