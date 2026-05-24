"""End-to-end tests for the admin settings routes (ADR-013 phase 4)."""

from collections.abc import Awaitable, Callable

import pytest
from httpx import AsyncClient

from src.modules.settings.domain.value_objects import (
    IntroDetectionConfig,
    ScanDedupConfig,
    SchedulerConfig,
)
from tests.modules.settings.e2e.conftest import SeededUser

LOGIN_PATH = "/api/v1/auth/cookie/login"
SETTINGS_ROOT = "/api/v1/admin/settings"


async def _login(client: AsyncClient, user: SeededUser) -> None:
    resp = await client.post(
        LOGIN_PATH,
        data={"username": user.email, "password": user.password},
    )
    assert resp.status_code == 204


async def _login_as_admin(
    client: AsyncClient,
    seed: Callable[..., Awaitable[SeededUser]],
) -> SeededUser:
    admin = await seed(email="admin@example.com", is_admin=True)
    await _login(client, admin)
    return admin


@pytest.mark.e2e
class TestAdminSettingsAuth:
    """Auth gate — ``current_admin_user`` rejects members + anon users."""

    async def test_unauthenticated_get_returns_401(self, client: AsyncClient) -> None:
        response = await client.get(SETTINGS_ROOT)
        assert response.status_code == 401

    async def test_member_get_returns_403(
        self,
        client: AsyncClient,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
    ) -> None:
        member = await seed_user_with_profile(email="member@example.com", is_admin=False)
        await _login(client, member)

        response = await client.get(SETTINGS_ROOT)

        assert response.status_code == 403

    async def test_member_patch_returns_403(
        self,
        client: AsyncClient,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
    ) -> None:
        member = await seed_user_with_profile(email="member@example.com", is_admin=False)
        await _login(client, member)

        response = await client.patch(
            f"{SETTINGS_ROOT}/scheduler",
            json=SchedulerConfig().model_dump(mode="json"),
        )

        assert response.status_code == 403


@pytest.mark.e2e
class TestAdminSettingsList:
    """``GET /admin/settings`` surfaces every bucket with synthesised defaults."""

    async def test_returns_one_entry_per_bucket_with_defaults(
        self,
        client: AsyncClient,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
    ) -> None:
        await _login_as_admin(client, seed_user_with_profile)

        response = await client.get(SETTINGS_ROOT)

        assert response.status_code == 200
        body = response.json()
        assert isinstance(body["data"], list)
        keys = sorted(d["key"] for d in body["data"])
        assert keys == sorted(
            [
                "scheduler",
                "thumbnail_backfill",
                "intro_detection",
                "streaming",
                "avatar",
                "scan_dedup",
            ]
        )
        for entry in body["data"]:
            assert entry["source"] == "default"
            assert entry["updated_at"] is None
            assert entry["updated_by_user_id"] is None

    async def test_reflects_admin_write_after_patch(
        self,
        client: AsyncClient,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
    ) -> None:
        admin = await _login_as_admin(client, seed_user_with_profile)

        patch_body = SchedulerConfig(enabled=False, reconcile_interval_minutes=10).model_dump(
            mode="json"
        )
        patch_resp = await client.patch(f"{SETTINGS_ROOT}/scheduler", json=patch_body)
        assert patch_resp.status_code == 200

        list_resp = await client.get(SETTINGS_ROOT)
        scheduler_entry = next(d for d in list_resp.json()["data"] if d["key"] == "scheduler")
        assert scheduler_entry["source"] == "admin"
        assert scheduler_entry["updated_by_user_id"] == admin.user_external_id
        assert scheduler_entry["updated_at"] is not None
        assert scheduler_entry["value"]["enabled"] is False
        assert scheduler_entry["value"]["reconcile_interval_minutes"] == 10


@pytest.mark.e2e
class TestAdminSettingsPatch:
    """``PATCH /admin/settings/<bucket>`` validates body + persists row."""

    async def test_full_replace_returns_persisted_detail(
        self,
        client: AsyncClient,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
    ) -> None:
        admin = await _login_as_admin(client, seed_user_with_profile)

        body = IntroDetectionConfig(min_confidence=0.85).model_dump(mode="json")
        response = await client.patch(f"{SETTINGS_ROOT}/intro-detection", json=body)

        assert response.status_code == 200
        payload = response.json()["data"]
        assert payload["key"] == "intro_detection"
        assert payload["source"] == "admin"
        assert payload["updated_by_user_id"] == admin.user_external_id
        assert payload["value"]["min_confidence"] == 0.85

    async def test_rejects_out_of_range_field(
        self,
        client: AsyncClient,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
    ) -> None:
        await _login_as_admin(client, seed_user_with_profile)

        # ``min_confidence`` is constrained to [0, 1] on the VO; FastAPI
        # validates the request body against ``IntroDetectionConfig``
        # before the handler runs.
        body = IntroDetectionConfig().model_dump(mode="json")
        body["min_confidence"] = 5.0
        response = await client.patch(f"{SETTINGS_ROOT}/intro-detection", json=body)

        assert response.status_code == 422

    async def test_rejects_cross_field_invariant_violation(
        self,
        client: AsyncClient,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
    ) -> None:
        await _login_as_admin(client, seed_user_with_profile)

        body = IntroDetectionConfig().model_dump(mode="json")
        body["min_intro_seconds"] = 200.0
        body["max_intro_seconds"] = 100.0
        response = await client.patch(f"{SETTINGS_ROOT}/intro-detection", json=body)

        assert response.status_code == 422

    async def test_repeat_patch_overwrites_previous_row(
        self,
        client: AsyncClient,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
    ) -> None:
        await _login_as_admin(client, seed_user_with_profile)

        first = SchedulerConfig(reconcile_interval_minutes=3).model_dump(mode="json")
        second = SchedulerConfig(reconcile_interval_minutes=7).model_dump(mode="json")

        await client.patch(f"{SETTINGS_ROOT}/scheduler", json=first)
        response = await client.patch(f"{SETTINGS_ROOT}/scheduler", json=second)

        assert response.status_code == 200
        list_resp = await client.get(SETTINGS_ROOT)
        scheduler_entry = next(d for d in list_resp.json()["data"] if d["key"] == "scheduler")
        assert scheduler_entry["value"]["reconcile_interval_minutes"] == 7

    async def test_scan_dedup_full_replace_persists_thresholds(
        self,
        client: AsyncClient,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
    ) -> None:
        admin = await _login_as_admin(client, seed_user_with_profile)

        body = ScanDedupConfig(
            runtime_delta_abs_minutes=3.0,
            runtime_delta_relative=0.05,
        ).model_dump(mode="json")
        response = await client.patch(f"{SETTINGS_ROOT}/scan-dedup", json=body)

        assert response.status_code == 200
        payload = response.json()["data"]
        assert payload["key"] == "scan_dedup"
        assert payload["source"] == "admin"
        assert payload["updated_by_user_id"] == admin.user_external_id
        assert payload["value"]["runtime_delta_abs_minutes"] == 3.0
        assert payload["value"]["runtime_delta_relative"] == 0.05

    async def test_scan_dedup_rejects_out_of_range_relative(
        self,
        client: AsyncClient,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
    ) -> None:
        await _login_as_admin(client, seed_user_with_profile)

        body = ScanDedupConfig().model_dump(mode="json")
        body["runtime_delta_relative"] = 1.5
        response = await client.patch(f"{SETTINGS_ROOT}/scan-dedup", json=body)

        assert response.status_code == 422
