"""Unit tests for :class:`LocalArtworkStorage`.

Exercises the adapter against a real temp directory (``tmp_path``) —
no mocking needed since the backend is the filesystem. Covers the
save → open round-trip, content-type derived from the key extension,
the not-found miss, idempotent delete, and the traversal guard.
"""

from __future__ import annotations

from pathlib import Path  # noqa: TCH003 — used by runtime fixture annotations

import pytest

from src.modules.media.infrastructure.storage.local_artwork_storage import (
    LocalArtworkStorage,
)


@pytest.fixture
def storage(tmp_path: Path) -> LocalArtworkStorage:
    """Adapter rooted at a test-scoped temp directory."""
    return LocalArtworkStorage(root_directory=str(tmp_path / "artwork"))


class TestSave:
    async def test_should_return_proxy_url_for_the_key(
        self, storage: LocalArtworkStorage
    ) -> None:
        url = await storage.save(content=b"bytes", content_type="image/jpeg", key="ab12.jpg")

        assert url == "/api/v1/artwork/ab12.jpg"

    async def test_should_write_bytes_under_the_root(
        self, storage: LocalArtworkStorage, tmp_path: Path
    ) -> None:
        await storage.save(content=b"poster", content_type="image/jpeg", key="k.jpg")

        assert (tmp_path / "artwork" / "k.jpg").read_bytes() == b"poster"


class TestOpen:
    async def test_should_round_trip_bytes_with_derived_content_type(
        self, storage: LocalArtworkStorage
    ) -> None:
        await storage.save(content=b"image-bytes", content_type="ignored", key="pic.png")

        result = await storage.open("pic.png")

        assert result is not None
        assert result.content == b"image-bytes"
        # Content type comes from the ``.png`` extension, not the
        # ``content_type`` passed to ``save``.
        assert result.content_type == "image/png"

    async def test_should_return_none_when_file_missing(
        self, storage: LocalArtworkStorage
    ) -> None:
        assert await storage.open("gone.jpg") is None

    async def test_should_fall_back_to_octet_stream_for_unknown_extension(
        self, storage: LocalArtworkStorage
    ) -> None:
        await storage.save(content=b"x", content_type="whatever", key="blob.unknownext")

        result = await storage.open("blob.unknownext")

        assert result is not None
        assert result.content_type == "application/octet-stream"


class TestDelete:
    async def test_should_remove_the_file(
        self, storage: LocalArtworkStorage, tmp_path: Path
    ) -> None:
        await storage.save(content=b"x", content_type="image/jpeg", key="k.jpg")

        await storage.delete("k.jpg")

        assert not (tmp_path / "artwork" / "k.jpg").exists()
        assert await storage.open("k.jpg") is None

    async def test_should_be_idempotent_when_file_missing(
        self, storage: LocalArtworkStorage
    ) -> None:
        # Must not raise.
        await storage.delete("never-existed.jpg")


class TestTraversalGuard:
    async def test_should_reject_key_escaping_the_root(
        self, storage: LocalArtworkStorage
    ) -> None:
        with pytest.raises(ValueError, match="escapes the storage root"):
            await storage.open("../secret.txt")
