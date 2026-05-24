"""Admin REST API for runtime-tunable settings (ADR-013 phase 4).

Surface for ``/admin/settings``: list every bucket + one PATCH per
bucket with full-replace semantics. Pydantic validation lives on the
configuration VOs themselves, so request bodies are typed against the
domain VO directly — keeps the API contract and the persisted shape in
sync without a duplicate schema layer.
"""

from dataclasses import asdict
from typing import Any

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends

from src.building_blocks.presentation import api_list, api_single
from src.config.containers import ApplicationContainer
from src.modules.identity.infrastructure.auth import current_admin_user
from src.modules.identity.infrastructure.persistence.models.user_model import UserModel
from src.modules.settings.application.dtos import UpdateSettingInput
from src.modules.settings.application.use_cases import (
    ListSettingsUseCase,
    UpdateSettingUseCase,
)
from src.modules.settings.domain.value_objects import (
    AvatarConfig,
    IntroDetectionConfig,
    ScanDedupConfig,
    SchedulerConfig,
    SettingKey,
    StreamingConfig,
    ThumbnailBackfillConfig,
)

router = APIRouter(prefix="/api/v1/admin/settings", tags=["Admin — Settings"])


@router.get("")
@inject
async def list_admin_settings(
    _admin: UserModel = Depends(current_admin_user),
    use_case: ListSettingsUseCase = Depends(
        Provide[ApplicationContainer.settings.list_settings],
    ),
) -> dict[str, Any]:
    """Return every settings bucket — persisted rows + synthesised defaults.

    Buckets that have never been written are surfaced with
    ``source='default'`` so the admin UI can show them in the same
    list as edited rows without a second request.
    """
    details = await use_case.execute()
    return api_list([asdict(d) for d in details])


@router.patch("/scheduler")
@inject
async def update_scheduler_settings(
    body: SchedulerConfig,
    admin: UserModel = Depends(current_admin_user),
    use_case: UpdateSettingUseCase = Depends(
        Provide[ApplicationContainer.settings.update_setting],
    ),
) -> dict[str, Any]:
    """Replace the persisted :class:`SchedulerConfig`."""
    detail = await use_case.execute(
        UpdateSettingInput(
            key=SettingKey.SCHEDULER.value,
            value=body.model_dump(mode="json"),
            acting_admin_id=admin.external_id,
        ),
    )
    return api_single("setting", asdict(detail))


@router.patch("/thumbnail-backfill")
@inject
async def update_thumbnail_backfill_settings(
    body: ThumbnailBackfillConfig,
    admin: UserModel = Depends(current_admin_user),
    use_case: UpdateSettingUseCase = Depends(
        Provide[ApplicationContainer.settings.update_setting],
    ),
) -> dict[str, Any]:
    """Replace the persisted :class:`ThumbnailBackfillConfig`."""
    detail = await use_case.execute(
        UpdateSettingInput(
            key=SettingKey.THUMBNAIL_BACKFILL.value,
            value=body.model_dump(mode="json"),
            acting_admin_id=admin.external_id,
        ),
    )
    return api_single("setting", asdict(detail))


@router.patch("/intro-detection")
@inject
async def update_intro_detection_settings(
    body: IntroDetectionConfig,
    admin: UserModel = Depends(current_admin_user),
    use_case: UpdateSettingUseCase = Depends(
        Provide[ApplicationContainer.settings.update_setting],
    ),
) -> dict[str, Any]:
    """Replace the persisted :class:`IntroDetectionConfig`."""
    detail = await use_case.execute(
        UpdateSettingInput(
            key=SettingKey.INTRO_DETECTION.value,
            value=body.model_dump(mode="json"),
            acting_admin_id=admin.external_id,
        ),
    )
    return api_single("setting", asdict(detail))


@router.patch("/streaming")
@inject
async def update_streaming_settings(
    body: StreamingConfig,
    admin: UserModel = Depends(current_admin_user),
    use_case: UpdateSettingUseCase = Depends(
        Provide[ApplicationContainer.settings.update_setting],
    ),
) -> dict[str, Any]:
    """Replace the persisted :class:`StreamingConfig`."""
    detail = await use_case.execute(
        UpdateSettingInput(
            key=SettingKey.STREAMING.value,
            value=body.model_dump(mode="json"),
            acting_admin_id=admin.external_id,
        ),
    )
    return api_single("setting", asdict(detail))


@router.patch("/avatar")
@inject
async def update_avatar_settings(
    body: AvatarConfig,
    admin: UserModel = Depends(current_admin_user),
    use_case: UpdateSettingUseCase = Depends(
        Provide[ApplicationContainer.settings.update_setting],
    ),
) -> dict[str, Any]:
    """Replace the persisted :class:`AvatarConfig`."""
    detail = await use_case.execute(
        UpdateSettingInput(
            key=SettingKey.AVATAR.value,
            value=body.model_dump(mode="json"),
            acting_admin_id=admin.external_id,
        ),
    )
    return api_single("setting", asdict(detail))


@router.patch("/scan-dedup")
@inject
async def update_scan_dedup_settings(
    body: ScanDedupConfig,
    admin: UserModel = Depends(current_admin_user),
    use_case: UpdateSettingUseCase = Depends(
        Provide[ApplicationContainer.settings.update_setting],
    ),
) -> dict[str, Any]:
    """Replace the persisted :class:`ScanDedupConfig`."""
    detail = await use_case.execute(
        UpdateSettingInput(
            key=SettingKey.SCAN_DEDUP.value,
            value=body.model_dump(mode="json"),
            acting_admin_id=admin.external_id,
        ),
    )
    return api_single("setting", asdict(detail))


__all__ = ["router"]
