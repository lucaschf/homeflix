"""Unit tests for :class:`ArtworkVariantService` (ADR-034).

In-memory fakes for storage and resizer pin the policy: serve a stored
variant, derive and store on a miss, never upscale, fall back to the
original when the resize or the store fails, single-flight concurrent
first hits, and best-effort pre-generation that never raises.
"""

from __future__ import annotations

import asyncio

from src.modules.metadata.application.ports.artwork_resizer_port import (
    ArtworkResizerPort,
    ResizedArtwork,
    UnsupportedArtworkImageError,
)
from src.modules.metadata.application.ports.artwork_storage_port import (
    ArtworkStoragePort,
    StoredArtwork,
)
from src.modules.metadata.application.services.artwork_variant_service import (
    ArtworkVariantService,
)
from src.modules.metadata.domain.value_objects.artwork_key import ArtworkKey
from src.modules.metadata.domain.value_objects.artwork_variant import ArtworkKind, ArtworkWidth

ORIGINAL = ArtworkKey("abc123.jpg")
W780 = ArtworkWidth(780)


class _FakeStorage(ArtworkStoragePort):
    def __init__(self, *, fail_save: bool = False) -> None:
        self.objects: dict[str, StoredArtwork] = {}
        self.saved: list[str] = []
        self._fail_save = fail_save

    async def save(self, *, content: bytes, content_type: str, key: str) -> str:
        if self._fail_save:
            raise OSError("disk full")
        self.objects[key] = StoredArtwork(content=content, content_type=content_type)
        self.saved.append(key)
        return f"/api/v1/artwork/{key}"

    async def open(self, key: str) -> StoredArtwork | None:
        return self.objects.get(key)

    async def delete(self, key: str) -> None:
        self.objects.pop(key, None)


class _FakeResizer(ArtworkResizerPort):
    def __init__(
        self,
        *,
        source_width: int = 4000,
        unsupported: bool = False,
        gate: asyncio.Event | None = None,
    ) -> None:
        self.calls: list[int] = []
        self._source_width = source_width
        self._unsupported = unsupported
        self._gate = gate

    async def resize(self, content: bytes, *, width: int) -> ResizedArtwork | None:
        self.calls.append(width)
        if self._gate is not None:
            await self._gate.wait()
        if self._unsupported:
            raise UnsupportedArtworkImageError("nope")
        if self._source_width <= width:
            return None
        return ResizedArtwork(content=f"w{width}".encode(), content_type="image/jpeg", width=width)


def _service(
    storage: _FakeStorage | None = None, resizer: _FakeResizer | None = None
) -> tuple[ArtworkVariantService, _FakeStorage, _FakeResizer]:
    storage = storage or _FakeStorage()
    resizer = resizer or _FakeResizer()
    return ArtworkVariantService(storage=storage, resizer=resizer), storage, resizer


async def _with_original(storage: _FakeStorage) -> None:
    await storage.save(content=b"original", content_type="image/jpeg", key=str(ORIGINAL))
    storage.saved.clear()


class TestEnsure:
    async def test_should_serve_a_stored_variant_without_resizing(self) -> None:
        service, storage, resizer = _service()
        await _with_original(storage)
        await storage.save(content=b"cached", content_type="image/jpeg", key="abc123.w780.jpg")

        result = await service.ensure(ORIGINAL, W780)

        assert result is not None
        assert result.content == b"cached"
        assert resizer.calls == []

    async def test_should_derive_store_and_return_the_variant_on_a_miss(self) -> None:
        service, storage, resizer = _service()
        await _with_original(storage)

        result = await service.ensure(ORIGINAL, W780)

        assert result is not None
        assert result.content == b"w780"
        assert resizer.calls == [780]
        assert storage.saved == ["abc123.w780.jpg"]

    async def test_should_serve_the_original_when_it_is_not_wider(self) -> None:
        service, storage, _ = _service(resizer=_FakeResizer(source_width=780))
        await _with_original(storage)

        result = await service.ensure(ORIGINAL, W780)

        assert result is not None
        assert result.content == b"original"
        assert storage.saved == []

    async def test_should_return_none_when_the_original_is_missing(self) -> None:
        service, _, resizer = _service()

        assert await service.ensure(ORIGINAL, W780) is None
        assert resizer.calls == []

    async def test_should_serve_the_original_when_it_cannot_be_resized(self) -> None:
        service, storage, _ = _service(resizer=_FakeResizer(unsupported=True))
        await _with_original(storage)

        result = await service.ensure(ORIGINAL, W780)

        assert result is not None
        assert result.content == b"original"
        assert storage.saved == []

    async def test_should_serve_the_original_when_the_variant_cannot_be_stored(self) -> None:
        storage = _FakeStorage()
        await _with_original(storage)
        storage._fail_save = True
        service, _, _ = _service(storage=storage)

        result = await service.ensure(ORIGINAL, W780)

        assert result is not None
        assert result.content == b"original"

    async def test_should_resize_once_for_concurrent_first_requests(self) -> None:
        gate = asyncio.Event()
        service, storage, resizer = _service(resizer=_FakeResizer(gate=gate))
        await _with_original(storage)

        tasks = [asyncio.create_task(service.ensure(ORIGINAL, W780)) for _ in range(5)]
        await asyncio.sleep(0)  # let every task reach the lock
        gate.set()
        results = await asyncio.gather(*tasks)

        assert [r.content for r in results if r is not None] == [b"w780"] * 5
        assert resizer.calls == [780]
        assert storage.saved == ["abc123.w780.jpg"]
        # The single-flight map is cleaned up once nobody holds the lock.
        assert service._locks == {}


class TestPregenerate:
    async def test_should_store_every_ladder_width_of_the_kind(self) -> None:
        service, storage, resizer = _service()

        await service.pregenerate(
            ORIGINAL, ArtworkKind.BACKDROP, content=b"original", content_type="image/jpeg"
        )

        assert resizer.calls == [780, 1280]
        assert storage.saved == ["abc123.w780.jpg", "abc123.w1280.jpg"]

    async def test_should_skip_widths_the_original_is_not_wider_than(self) -> None:
        service, storage, _ = _service(resizer=_FakeResizer(source_width=1000))

        await service.pregenerate(
            ORIGINAL, ArtworkKind.BACKDROP, content=b"original", content_type="image/jpeg"
        )

        assert storage.saved == ["abc123.w780.jpg"]

    async def test_should_swallow_resize_and_store_failures(self) -> None:
        unsupported, _, _ = _service(resizer=_FakeResizer(unsupported=True))
        failing_store, _, _ = _service(storage=_FakeStorage(fail_save=True))

        for service in (unsupported, failing_store):
            await service.pregenerate(
                ORIGINAL, ArtworkKind.POSTER, content=b"original", content_type="image/jpeg"
            )
