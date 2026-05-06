"""Local-disk implementation of ``AvatarStoragePort``.

Validates the uploaded bytes via Pillow (the declared MIME from the
form is untrusted), centre-crops to a square and resizes to the
configured side length, then persists as WebP under
``{thumbnails_directory}/{avatar_storage_subdir}/{profile_id}.webp``.

WebP balances size and quality well for small avatars (a 256x256
photo lands around 15-30 KB). Saving in a single canonical format
also lets the GET route hard-code the response media type instead
of round-tripping the original.
"""

from __future__ import annotations

import asyncio
import io
from datetime import UTC, datetime
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from src.config.logging import get_logger
from src.modules.identity.application.ports.avatar_storage_port import (
    AvatarStoragePort,
    AvatarTooLargeError,
    InvalidAvatarImageError,
)

_logger = get_logger()

# MIMEs the catalogue accepts at the form boundary. The actual
# bytes are still verified by Pillow — the declared MIME is just an
# early reject hint, not a trust anchor.
_ALLOWED_MIME_TYPES = frozenset(
    {
        "image/jpeg",
        "image/png",
        "image/webp",
    }
)

# Pillow format names (independent of MIME). What we accept after
# decoding the actual bytes — keeps the surface honest if a client
# claims ``image/jpeg`` but uploads a TIFF.
_ALLOWED_PIL_FORMATS = frozenset({"JPEG", "PNG", "WEBP"})

# WebP quality. Pillow's default for quality is 80; bumping to 85
# keeps faces and skin tones crisp without bloating the file
# beyond a few dozen KB at 256x256.
_WEBP_QUALITY = 85


class LocalAvatarStorage(AvatarStoragePort):
    """Resize uploaded avatars and write WebP files to local disk."""

    def __init__(
        self,
        *,
        root_directory: str,
        subdirectory: str,
        max_size_mb: int,
        side_length: int,
    ) -> None:
        self._directory = Path(root_directory) / subdirectory
        self._max_size_bytes = max_size_mb * 1024 * 1024
        self._side_length = side_length

    async def save(
        self,
        profile_id: str,
        *,
        content: bytes,
        declared_mime_type: str,
    ) -> str:
        """Validate + resize + persist + return the cache-busted URL."""
        if len(content) > self._max_size_bytes:
            raise AvatarTooLargeError(
                f"avatar exceeds {self._max_size_bytes} byte cap " f"(got {len(content)} bytes)"
            )
        if declared_mime_type not in _ALLOWED_MIME_TYPES:
            raise InvalidAvatarImageError(
                f"declared mime type {declared_mime_type!r} is not in the "
                f"allow-list {sorted(_ALLOWED_MIME_TYPES)}"
            )

        # Pillow work is CPU-bound — ``asyncio.to_thread`` avoids
        # blocking the event loop on JPEG decode + resize for a
        # 2 MB image (a few hundred ms on a modern phone shot).
        target_path = self._target_path(profile_id)
        await asyncio.to_thread(
            self._decode_resize_and_save,
            content,
            target_path,
        )

        timestamp = int(datetime.now(UTC).timestamp())
        return f"/api/v1/profiles/{profile_id}/avatar?v={timestamp}"

    async def delete(self, profile_id: str) -> None:
        """Remove the persisted file. Idempotent — no error when absent."""
        target_path = self._target_path(profile_id)
        try:
            await asyncio.to_thread(target_path.unlink)
        except FileNotFoundError:
            return
        except OSError as exc:
            # Filesystem hiccup; log and let the caller continue —
            # the avatar URL is being cleared in the same UoW
            # whether or not the file removal succeeded, so a
            # leaked file is the worst outcome.
            _logger.warning(
                "[identity] failed to remove avatar file",
                profile_id=profile_id,
                path=str(target_path),
                error=str(exc),
            )

    def _target_path(self, profile_id: str) -> Path:
        """Resolve the on-disk path for a profile's avatar."""
        return self._directory / f"{profile_id}.webp"

    def _decode_resize_and_save(self, content: bytes, target_path: Path) -> None:
        """Synchronous Pillow work — open, validate, crop, scale, save."""
        try:
            with Image.open(io.BytesIO(content)) as source:
                if source.format not in _ALLOWED_PIL_FORMATS:
                    raise InvalidAvatarImageError(
                        f"image format {source.format!r} is not supported"
                    )
                # Force-load the image data so any decode error
                # surfaces synchronously inside this except branch
                # rather than later when ``copy()`` reads pixels.
                source.load()
                cropped = self._centre_crop_square(source)
                resized = cropped.resize(
                    (self._side_length, self._side_length),
                    resample=Image.Resampling.LANCZOS,
                )
                target_path.parent.mkdir(parents=True, exist_ok=True)
                # Always save as WebP — single canonical format
                # simplifies the GET route's media_type and keeps
                # the file extension predictable.
                resized.save(target_path, format="WEBP", quality=_WEBP_QUALITY)
        except UnidentifiedImageError as exc:
            raise InvalidAvatarImageError(
                "uploaded bytes did not decode as a known image format"
            ) from exc

    def _centre_crop_square(self, image: Image.Image) -> Image.Image:
        """Crop ``image`` to its largest centred square."""
        width, height = image.size
        if width == height:
            return image
        side = min(width, height)
        left = (width - side) // 2
        top = (height - side) // 2
        return image.crop((left, top, left + side, top + side))


__all__ = ["LocalAvatarStorage"]
