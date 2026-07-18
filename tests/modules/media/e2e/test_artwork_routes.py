"""End-to-end tests for the artwork proxy route (ADR-029).

Drives ``GET /api/v1/artwork/{key}`` over the in-process ASGI
transport with an in-memory fake :class:`ArtworkStoragePort` swapped
into the media container. Covers the hit, the not-yet-mirrored miss
(404 vs. redirect-to-origin), and the invalid-key guard. The route is
deliberately unauthenticated, so no login is needed.
"""

from __future__ import annotations

from collections.abc import (  # noqa: TCH003 — used by runtime fixture annotations
    AsyncGenerator,
)

import pytest
from dependency_injector import providers
from fastapi import FastAPI  # noqa: TCH002 — used by runtime fixture annotations
from httpx import AsyncClient  # noqa: TCH002 — used by runtime fixture annotations

from src.modules.media.application.ports.artwork_storage_port import (
    ArtworkStoragePort,
    StoredArtwork,
)

ARTWORK_PATH = "/api/v1/artwork/{key}"


class _FakeArtworkStorage(ArtworkStoragePort):
    """In-memory port double keyed by object key."""

    def __init__(self) -> None:
        self._objects: dict[str, StoredArtwork] = {}

    async def save(self, *, content: bytes, content_type: str, key: str) -> str:
        self._objects[key] = StoredArtwork(content=content, content_type=content_type)
        return f"/api/v1/artwork/{key}"

    async def open(self, key: str) -> StoredArtwork | None:
        return self._objects.get(key)

    async def delete(self, key: str) -> None:
        self._objects.pop(key, None)


@pytest.fixture(scope="function")
async def storage(app: FastAPI) -> AsyncGenerator[_FakeArtworkStorage, None]:
    """Override the media container's artwork storage with a fake."""
    fake = _FakeArtworkStorage()
    app.state.container.media.artwork_storage.override(providers.Object(fake))
    yield fake
    app.state.container.media.artwork_storage.reset_override()


class TestGetArtwork:
    async def test_should_serve_stored_bytes_with_content_type(
        self, client: AsyncClient, storage: _FakeArtworkStorage
    ) -> None:
        await storage.save(content=b"poster-bytes", content_type="image/jpeg", key="ab12.jpg")

        resp = await client.get(ARTWORK_PATH.format(key="ab12.jpg"))

        assert resp.status_code == 200
        assert resp.content == b"poster-bytes"
        assert resp.headers["content-type"] == "image/jpeg"
        assert "immutable" in resp.headers["cache-control"]

    async def test_should_404_when_not_mirrored_and_no_origin(
        self, client: AsyncClient, storage: _FakeArtworkStorage
    ) -> None:
        resp = await client.get(ARTWORK_PATH.format(key="missing.jpg"))

        assert resp.status_code == 404

    async def test_should_redirect_to_origin_when_not_mirrored(
        self, client: AsyncClient, storage: _FakeArtworkStorage
    ) -> None:
        origin = "https://image.tmdb.org/t/p/original/x.jpg"

        resp = await client.get(
            ARTWORK_PATH.format(key="missing.jpg"),
            params={"origin": origin},
            follow_redirects=False,
        )

        assert resp.status_code == 302
        assert resp.headers["location"] == origin

    async def test_should_400_on_invalid_key(
        self, client: AsyncClient, storage: _FakeArtworkStorage
    ) -> None:
        # A slash-bearing key can't even reach the handler as one path
        # segment, so probe the charset guard with a traversal attempt
        # that stays within a single segment.
        resp = await client.get(ARTWORK_PATH.format(key="bad%20key"))

        assert resp.status_code == 400
