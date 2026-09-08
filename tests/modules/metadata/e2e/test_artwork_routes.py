"""End-to-end tests for the artwork proxy route (ADR-029, ADR-034).

Drives ``GET /api/v1/artwork/{key}`` over the in-process ASGI
transport with an in-memory fake :class:`ArtworkStoragePort` swapped
into the media container. Covers the hit, the not-yet-mirrored miss
(404 vs. redirect-to-origin), the invalid-key guard, and the ``?w=``
variant path (derive-on-first-use, cache, no-upscale, the 400s). The
route is deliberately unauthenticated, so no login is needed.
"""

from __future__ import annotations

from collections.abc import (  # noqa: TCH003 — used by runtime fixture annotations
    AsyncGenerator,
)
from io import BytesIO

import pytest
from dependency_injector import providers
from fastapi import FastAPI  # noqa: TCH002 — used by runtime fixture annotations
from httpx import AsyncClient  # noqa: TCH002 — used by runtime fixture annotations
from PIL import Image

from src.modules.metadata.application.ports.artwork_resizer_port import (
    ArtworkResizerPort,
    ResizedArtwork,
)
from src.modules.metadata.application.ports.artwork_storage_port import (
    ArtworkStoragePort,
    StoredArtwork,
)
from src.modules.metadata.infrastructure.pillow_artwork_resizer import PillowArtworkResizer

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


class _FakeResizer(ArtworkResizerPort):
    """Counts calls; returns fixed bytes, or ``None`` when the source is too narrow."""

    def __init__(self, *, source_width: int = 4000) -> None:
        self.calls: list[int] = []
        self._source_width = source_width

    async def resize(self, content: bytes, *, width: int) -> ResizedArtwork | None:
        self.calls.append(width)
        if self._source_width <= width:
            return None
        return ResizedArtwork(content=b"resized", content_type="image/jpeg", width=width)


@pytest.fixture(scope="function")
async def storage(app: FastAPI) -> AsyncGenerator[_FakeArtworkStorage, None]:
    """Override the media container's artwork storage with a fake."""
    fake = _FakeArtworkStorage()
    app.state.container.metadata.artwork_storage.override(providers.Object(fake))
    yield fake
    app.state.container.metadata.artwork_storage.reset_override()


@pytest.fixture(scope="function")
async def resizer(app: FastAPI) -> AsyncGenerator[_FakeResizer, None]:
    """Override the resizer with a counting fake, before the first request resolves it."""
    fake = _FakeResizer()
    app.state.container.metadata.artwork_resizer.override(providers.Object(fake))
    yield fake
    app.state.container.metadata.artwork_resizer.reset_override()


def _override_resizer(app: FastAPI, resizer: ArtworkResizerPort) -> None:
    app.state.container.metadata.artwork_resizer.override(providers.Object(resizer))


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

    async def test_should_redirect_to_allowed_origin_when_not_mirrored(
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

    async def test_should_404_not_redirect_when_origin_host_not_allowed(
        self, client: AsyncClient, storage: _FakeArtworkStorage
    ) -> None:
        # An arbitrary origin host must never be echoed into Location —
        # that would make this public endpoint an open redirect.
        resp = await client.get(
            ARTWORK_PATH.format(key="missing.jpg"),
            params={"origin": "https://evil.example.com/x.jpg"},
            follow_redirects=False,
        )

        assert resp.status_code == 404

    async def test_should_serve_stored_bytes_even_when_origin_supplied(
        self, client: AsyncClient, storage: _FakeArtworkStorage
    ) -> None:
        # Precedence: a mirrored object wins over the origin fallback —
        # never redirect away from a good local image.
        await storage.save(content=b"local", content_type="image/jpeg", key="ab12.jpg")

        resp = await client.get(
            ARTWORK_PATH.format(key="ab12.jpg"),
            params={"origin": "https://image.tmdb.org/t/p/original/x.jpg"},
            follow_redirects=False,
        )

        assert resp.status_code == 200
        assert resp.content == b"local"

    async def test_should_serve_without_authentication(
        self, client: AsyncClient, storage: _FakeArtworkStorage
    ) -> None:
        # Deliberate design: artwork is public <img> imagery that cannot
        # carry auth headers. This pins the invariant so adding an auth
        # dependency to the router would fail here by name.
        await storage.save(content=b"x", content_type="image/png", key="pub.png")

        resp = await client.get(ARTWORK_PATH.format(key="pub.png"))

        assert resp.status_code == 200

    async def test_should_400_on_invalid_key(
        self, client: AsyncClient, storage: _FakeArtworkStorage
    ) -> None:
        # A slash-bearing key can't even reach the handler as one path
        # segment, so probe the charset guard with a space (percent-
        # encoded) that stays within a single path segment.
        resp = await client.get(ARTWORK_PATH.format(key="bad%20key"))

        assert resp.status_code == 400
        # Assert the 400 came from the charset guard specifically, not
        # some other validation, so the test can't pass for a wrong reason.
        # The HTTPException detail lands in the envelope's ``message``.
        assert resp.json()["message"] == "invalid artwork key"

    async def test_should_400_on_all_dots_key(
        self, client: AsyncClient, storage: _FakeArtworkStorage
    ) -> None:
        # All-dots keys pass the charset regex (dots are allowed) but are
        # not valid objects and would reach storage as a directory /
        # traversal-shaped path — must be rejected up front, not 500.
        # ``...`` is used (not ``.``/``..``) because the server URL-
        # normalizes the latter before routing, so they never reach the
        # handler; ``...`` is an ordinary segment that does.
        resp = await client.get(ARTWORK_PATH.format(key="..."))

        assert resp.status_code == 400
        assert resp.json()["message"] == "invalid artwork key"


class TestGetArtworkVariant:
    async def test_should_derive_store_and_serve_the_variant(
        self, client: AsyncClient, storage: _FakeArtworkStorage, resizer: _FakeResizer
    ) -> None:
        await storage.save(content=b"original", content_type="image/jpeg", key="ab12.jpg")

        resp = await client.get(ARTWORK_PATH.format(key="ab12.jpg"), params={"w": 780})

        assert resp.status_code == 200
        assert resp.content == b"resized"
        assert "immutable" in resp.headers["cache-control"]
        assert resizer.calls == [780]
        # Stored under the variant key, next to the untouched original.
        assert (await storage.open("ab12.w780.jpg")) is not None
        original = await storage.open("ab12.jpg")
        assert original is not None
        assert original.content == b"original"

    async def test_should_serve_a_stored_variant_without_resizing_again(
        self, client: AsyncClient, storage: _FakeArtworkStorage, resizer: _FakeResizer
    ) -> None:
        await storage.save(content=b"original", content_type="image/jpeg", key="ab12.jpg")
        await client.get(ARTWORK_PATH.format(key="ab12.jpg"), params={"w": 780})

        resp = await client.get(ARTWORK_PATH.format(key="ab12.jpg"), params={"w": 780})

        assert resp.status_code == 200
        assert resp.content == b"resized"
        assert resizer.calls == [780]

    async def test_should_serve_the_original_when_it_is_not_wider(
        self, client: AsyncClient, storage: _FakeArtworkStorage, app: FastAPI
    ) -> None:
        _override_resizer(app, _FakeResizer(source_width=500))
        await storage.save(content=b"original", content_type="image/jpeg", key="ab12.jpg")

        resp = await client.get(ARTWORK_PATH.format(key="ab12.jpg"), params={"w": 1280})

        assert resp.status_code == 200
        assert resp.content == b"original"
        # Never upscale, never store an upscale.
        assert (await storage.open("ab12.w1280.jpg")) is None

    async def test_should_really_downscale_with_pillow(
        self, client: AsyncClient, storage: _FakeArtworkStorage, app: FastAPI
    ) -> None:
        _override_resizer(app, PillowArtworkResizer())
        buffer = BytesIO()
        Image.new("RGBA", (1600, 900), (10, 20, 30, 128)).save(buffer, format="PNG")
        await storage.save(content=buffer.getvalue(), content_type="image/png", key="wide.png")

        resp = await client.get(ARTWORK_PATH.format(key="wide.png"), params={"w": 780})

        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/png"
        with Image.open(BytesIO(resp.content)) as served:
            assert served.width == 780
            assert served.mode == "RGBA"

    async def test_should_400_on_an_off_ladder_width(
        self, client: AsyncClient, storage: _FakeArtworkStorage, resizer: _FakeResizer
    ) -> None:
        await storage.save(content=b"original", content_type="image/jpeg", key="ab12.jpg")

        resp = await client.get(ARTWORK_PATH.format(key="ab12.jpg"), params={"w": 999})

        assert resp.status_code == 400
        assert resp.json()["message"] == "unsupported artwork width"
        assert resizer.calls == []

    async def test_should_400_on_a_variant_of_a_variant(
        self, client: AsyncClient, storage: _FakeArtworkStorage, resizer: _FakeResizer
    ) -> None:
        await storage.save(content=b"resized", content_type="image/jpeg", key="ab12.w780.jpg")

        resp = await client.get(ARTWORK_PATH.format(key="ab12.w780.jpg"), params={"w": 500})

        assert resp.status_code == 400
        assert resp.json()["message"] == "cannot derive a variant of a variant"

    async def test_should_fall_back_to_origin_when_the_original_is_missing(
        self, client: AsyncClient, storage: _FakeArtworkStorage, resizer: _FakeResizer
    ) -> None:
        origin = "https://image.tmdb.org/t/p/original/x.jpg"

        resp = await client.get(
            ARTWORK_PATH.format(key="missing.jpg"),
            params={"w": 780, "origin": origin},
            follow_redirects=False,
        )

        assert resp.status_code == 302
        assert resp.headers["location"] == origin

    async def test_should_404_when_the_original_is_missing_and_no_origin(
        self, client: AsyncClient, storage: _FakeArtworkStorage, resizer: _FakeResizer
    ) -> None:
        resp = await client.get(ARTWORK_PATH.format(key="missing.jpg"), params={"w": 780})

        assert resp.status_code == 404
