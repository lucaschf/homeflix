"""Integration tests for the local-disk avatar storage adapter.

These tests exercise the real Pillow decode + resize + WebP encode
path against a temporary directory; nothing here mocks the file
system.
"""

from __future__ import annotations

import io
from pathlib import Path  # noqa: TCH003 — used by runtime fixture annotations
from unittest.mock import AsyncMock

import pytest
from PIL import Image

from src.modules.identity.application.ports import (
    AvatarTooLargeError,
    InvalidAvatarImageError,
)
from src.modules.identity.infrastructure.storage import LocalAvatarStorage
from src.modules.settings.domain.value_objects import AvatarConfig

_PROFILE_ID = "prf_test12345678"


def _png_bytes(
    width: int = 600, height: int = 400, *, colour: tuple[int, int, int] = (255, 100, 50)
) -> bytes:
    """Generate a tiny in-memory PNG so tests don't need fixture files."""
    img = Image.new("RGB", (width, height), colour)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _fake_runtime_settings(*, max_size_mb: int = 2, side: int = 256) -> AsyncMock:
    runtime = AsyncMock()
    runtime.avatar = AsyncMock(
        return_value=AvatarConfig(
            storage_subdir=".homeflix/avatars",
            max_size_mb=max_size_mb,
            size_pixels=side,
        ),
    )
    return runtime


def _make_storage(tmp_path: Path, *, max_size_mb: int = 2, side: int = 256) -> LocalAvatarStorage:
    return LocalAvatarStorage(
        _fake_runtime_settings(max_size_mb=max_size_mb, side=side),
        root_directory=str(tmp_path),
    )


@pytest.mark.integration
class TestLocalAvatarStorage:
    async def test_should_persist_resized_webp(self, tmp_path: Path) -> None:
        storage = _make_storage(tmp_path)

        url = await storage.save(
            _PROFILE_ID,
            content=_png_bytes(width=800, height=600),
            declared_mime_type="image/png",
        )

        assert url.startswith(f"/api/v1/profiles/{_PROFILE_ID}/avatar?v=")

        # File landed at the deterministic path with WebP extension.
        target = tmp_path / ".homeflix" / "avatars" / f"{_PROFILE_ID}.webp"
        assert target.is_file()

        # Open back via Pillow to confirm it really is a 256x256 WebP.
        with Image.open(target) as roundtrip:
            assert roundtrip.format == "WEBP"
            assert roundtrip.size == (256, 256)

    async def test_should_centre_crop_non_square_inputs(self, tmp_path: Path) -> None:
        # A 800x400 PNG should crop to 400x400 then scale to 256x256.
        storage = _make_storage(tmp_path)
        await storage.save(
            _PROFILE_ID,
            content=_png_bytes(width=800, height=400),
            declared_mime_type="image/png",
        )
        target = tmp_path / ".homeflix" / "avatars" / f"{_PROFILE_ID}.webp"
        with Image.open(target) as roundtrip:
            assert roundtrip.size == (256, 256)

    async def test_should_reject_payload_above_size_cap(self, tmp_path: Path) -> None:
        # 1 MB cap, send 2 MB worth of bytes — fails before Pillow runs.
        storage = _make_storage(tmp_path, max_size_mb=1)
        oversized = b"\x00" * (2 * 1024 * 1024)

        with pytest.raises(AvatarTooLargeError):
            await storage.save(
                _PROFILE_ID,
                content=oversized,
                declared_mime_type="image/png",
            )
        target = tmp_path / ".homeflix" / "avatars" / f"{_PROFILE_ID}.webp"
        assert not target.exists()

    async def test_should_reject_non_image_payload(self, tmp_path: Path) -> None:
        storage = _make_storage(tmp_path)

        with pytest.raises(InvalidAvatarImageError):
            await storage.save(
                _PROFILE_ID,
                content=b"this is not an image at all",
                declared_mime_type="image/png",
            )

    async def test_should_reject_disallowed_mime_type(self, tmp_path: Path) -> None:
        # GIF is intentionally NOT in the allow-list (avatars are
        # static; no point honouring an animated GIF upload).
        storage = _make_storage(tmp_path)

        with pytest.raises(InvalidAvatarImageError):
            await storage.save(
                _PROFILE_ID,
                content=_png_bytes(),
                declared_mime_type="image/gif",
            )

    async def test_re_upload_should_overwrite_previous_file(self, tmp_path: Path) -> None:
        storage = _make_storage(tmp_path)

        # First upload — orange tile
        await storage.save(
            _PROFILE_ID,
            content=_png_bytes(colour=(255, 100, 50)),
            declared_mime_type="image/png",
        )
        # Second upload — blue tile, same profile id
        await storage.save(
            _PROFILE_ID,
            content=_png_bytes(colour=(50, 100, 255)),
            declared_mime_type="image/png",
        )

        target = tmp_path / ".homeflix" / "avatars" / f"{_PROFILE_ID}.webp"
        assert target.is_file()
        with Image.open(target) as roundtrip:
            # Pixel at the centre should reflect the SECOND upload's
            # colour palette (after WebP compression at quality 85
            # the channels are close to but not exactly the input).
            r, g, b = roundtrip.convert("RGB").getpixel((128, 128))
            assert b > r  # Blue dominant — second upload won.

    async def test_delete_should_be_idempotent(self, tmp_path: Path) -> None:
        storage = _make_storage(tmp_path)

        # Delete before any upload — must not raise.
        await storage.delete(_PROFILE_ID)

        # Save then delete then delete again — the second delete is a no-op.
        await storage.save(
            _PROFILE_ID,
            content=_png_bytes(),
            declared_mime_type="image/png",
        )
        target = tmp_path / ".homeflix" / "avatars" / f"{_PROFILE_ID}.webp"
        assert target.is_file()

        await storage.delete(_PROFILE_ID)
        assert not target.exists()

        await storage.delete(_PROFILE_ID)
