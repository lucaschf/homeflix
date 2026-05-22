"""End-to-end tests for the profile-avatar routes.

Drives ``POST /api/v1/profiles/{id}/avatar``,
``DELETE /api/v1/profiles/{id}/avatar`` and
``GET /api/v1/profiles/{id}/avatar`` over the in-process ASGI
transport. The avatar storage is overridden to write under a
test-scoped ``tmp_path`` so the assertions can read the real WebP
file back.
"""

from __future__ import annotations

import io
from collections.abc import (  # noqa: TCH003 — used by runtime fixture annotations
    Awaitable,
    Callable,
)
from pathlib import Path  # noqa: TCH003 — used by runtime fixture annotations

import pytest
from dependency_injector import providers
from fastapi import FastAPI  # noqa: TCH002 — used by runtime fixture annotations
from httpx import AsyncClient  # noqa: TCH002 — used by runtime fixture annotations
from PIL import Image

from src.modules.identity.infrastructure.storage import LocalAvatarStorage
from tests.modules.identity.e2e.conftest import (
    SeededUser,  # noqa: TCH001 — used by runtime annotations
)

LOGIN_PATH = "/api/v1/auth/cookie/login"
AVATAR_PATH = "/api/v1/profiles/{profile_id}/avatar"


def _png_bytes(width: int = 600, height: int = 400) -> bytes:
    img = Image.new("RGB", (width, height), (217, 119, 87))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture(scope="function")
def app_with_tmp_avatar_storage(app: FastAPI, tmp_path: Path) -> FastAPI:
    """Override the identity container's avatar storage to a tempdir."""
    from unittest.mock import AsyncMock

    from src.modules.settings.domain.value_objects import AvatarConfig

    runtime_settings = AsyncMock()
    runtime_settings.avatar = AsyncMock(
        return_value=AvatarConfig(
            storage_subdir=".homeflix/avatars",
            max_size_mb=2,
            size_pixels=64,  # tiny for faster Pillow round-trip
        ),
    )
    storage = LocalAvatarStorage(
        runtime_settings,
        root_directory=str(tmp_path),
    )
    app.state.container.identity.avatar_storage.override(providers.Object(storage))
    # The GET route resolves the file path by asking the same
    # ``avatar_storage`` instance (``resolve_path``), so the override
    # above is enough — no separate Settings tweak required.
    yield app
    app.state.container.identity.avatar_storage.reset_override()


async def _login(client: AsyncClient, user: SeededUser) -> None:
    resp = await client.post(LOGIN_PATH, data={"username": user.email, "password": user.password})
    assert resp.status_code == 204


class TestUploadAvatar:
    async def test_should_persist_and_return_avatar_url(
        self,
        client: AsyncClient,
        app_with_tmp_avatar_storage: FastAPI,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
        tmp_path: Path,
    ) -> None:
        user = await seed_user_with_profile()
        await _login(client, user)

        files = {"file": ("photo.png", _png_bytes(), "image/png")}
        resp = await client.post(
            AVATAR_PATH.format(profile_id=user.profile_external_id), files=files
        )

        assert resp.status_code == 200
        body = resp.json()["data"]
        assert body["id"] == user.profile_external_id
        assert body["avatar_url"] is not None
        assert body["avatar_url"].startswith(
            f"/api/v1/profiles/{user.profile_external_id}/avatar?v="
        )
        # File landed on disk under the test-scoped tempdir.
        target = tmp_path / ".homeflix" / "avatars" / f"{user.profile_external_id}.webp"
        assert target.is_file()

    async def test_should_return_413_when_payload_is_too_large(
        self,
        client: AsyncClient,
        app_with_tmp_avatar_storage: FastAPI,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
    ) -> None:
        user = await seed_user_with_profile()
        await _login(client, user)

        oversized = b"\x00" * (3 * 1024 * 1024)
        files = {"file": ("huge.png", oversized, "image/png")}
        resp = await client.post(
            AVATAR_PATH.format(profile_id=user.profile_external_id), files=files
        )

        assert resp.status_code == 413

    async def test_should_return_415_for_disallowed_mime(
        self,
        client: AsyncClient,
        app_with_tmp_avatar_storage: FastAPI,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
    ) -> None:
        user = await seed_user_with_profile()
        await _login(client, user)

        files = {"file": ("animated.gif", _png_bytes(), "image/gif")}
        resp = await client.post(
            AVATAR_PATH.format(profile_id=user.profile_external_id), files=files
        )

        assert resp.status_code == 415

    async def test_should_return_415_when_bytes_are_not_an_image(
        self,
        client: AsyncClient,
        app_with_tmp_avatar_storage: FastAPI,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
    ) -> None:
        user = await seed_user_with_profile()
        await _login(client, user)

        files = {"file": ("nope.png", b"definitely not an image", "image/png")}
        resp = await client.post(
            AVATAR_PATH.format(profile_id=user.profile_external_id), files=files
        )

        assert resp.status_code == 415

    async def test_should_return_401_when_unauthenticated(
        self,
        client: AsyncClient,
        app_with_tmp_avatar_storage: FastAPI,
    ) -> None:
        files = {"file": ("photo.png", _png_bytes(), "image/png")}
        resp = await client.post("/api/v1/profiles/prf_anything/avatar", files=files)
        assert resp.status_code == 401


class TestDeleteAvatar:
    async def test_should_clear_avatar_url_and_remove_file(
        self,
        client: AsyncClient,
        app_with_tmp_avatar_storage: FastAPI,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
        tmp_path: Path,
    ) -> None:
        user = await seed_user_with_profile()
        await _login(client, user)

        # Upload first so there's something to delete.
        await client.post(
            AVATAR_PATH.format(profile_id=user.profile_external_id),
            files={"file": ("photo.png", _png_bytes(), "image/png")},
        )

        resp = await client.delete(AVATAR_PATH.format(profile_id=user.profile_external_id))

        assert resp.status_code == 200
        assert resp.json()["data"]["avatar_url"] is None
        target = tmp_path / ".homeflix" / "avatars" / f"{user.profile_external_id}.webp"
        assert not target.exists()

    async def test_should_be_idempotent_when_no_avatar_exists(
        self,
        client: AsyncClient,
        app_with_tmp_avatar_storage: FastAPI,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
    ) -> None:
        user = await seed_user_with_profile()
        await _login(client, user)

        # No prior upload.
        resp = await client.delete(AVATAR_PATH.format(profile_id=user.profile_external_id))

        assert resp.status_code == 200
        assert resp.json()["data"]["avatar_url"] is None
