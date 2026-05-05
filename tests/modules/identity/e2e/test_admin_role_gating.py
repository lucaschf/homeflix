"""End-to-end tests for the admin role gate.

Drives ``POST /api/v1/libraries`` (a representative gated endpoint)
as both an admin user and a regular member to confirm
``current_admin_user`` is wired through and returns the standard
403 envelope for members. Other gated endpoints (scan, enrichment,
intro markers, file management, HLS cache flush) reuse the same dep,
so a single representative check is enough — duplicating the matrix
across every route would test FastAPI's dependency mechanics, not
our code.
"""

from collections.abc import Awaitable, Callable

from httpx import AsyncClient

from tests.modules.identity.e2e.conftest import SeededUser

LOGIN_PATH = "/api/v1/auth/cookie/login"
LIBRARIES_PATH = "/api/v1/libraries"

_VALID_LIBRARY_BODY = {
    "name": "Movies",
    "library_type": "movies",
    "paths": ["/tmp/movies"],
    "language": "en",
    "metadata_providers": [{"provider": "tmdb", "priority": 1, "enabled": True}],
    "scan_schedule": None,
    "settings": {
        "preferred_audio_language": "en",
        "preferred_subtitle_language": "en",
        "subtitle_mode": "none",
        "generate_thumbnails": True,
        "detect_intros": True,
        "auto_refresh_metadata": True,
    },
}


async def _login(client: AsyncClient, user: SeededUser) -> None:
    resp = await client.post(
        LOGIN_PATH,
        data={"username": user.email, "password": user.password},
    )
    assert resp.status_code == 204


class TestAdminRoleGating:
    async def test_should_return_403_when_member_calls_admin_endpoint(
        self,
        client: AsyncClient,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
    ) -> None:
        member = await seed_user_with_profile(email="member@example.com", is_admin=False)
        await _login(client, member)

        response = await client.post(LIBRARIES_PATH, json=_VALID_LIBRARY_BODY)

        assert response.status_code == 403

    async def test_should_allow_admin_to_call_admin_endpoint(
        self,
        client: AsyncClient,
        seed_user_with_profile: Callable[..., Awaitable[SeededUser]],
    ) -> None:
        admin = await seed_user_with_profile(email="admin@example.com", is_admin=True)
        await _login(client, admin)

        response = await client.post(LIBRARIES_PATH, json=_VALID_LIBRARY_BODY)

        # Library creation succeeds — proves the gate let the admin
        # through; deeper library semantics live in the library e2e
        # suite. (Library POST returns 200 with the body, not 201;
        # both signal success here.)
        assert response.status_code in (200, 201)

    async def test_should_return_401_when_unauthenticated(
        self,
        client: AsyncClient,
    ) -> None:
        response = await client.post(LIBRARIES_PATH, json=_VALID_LIBRARY_BODY)

        # ``current_admin_user`` composes on top of
        # ``current_active_user`` so the unauthenticated path stays
        # 401, not 403 — the cookie check fires first.
        assert response.status_code == 401
