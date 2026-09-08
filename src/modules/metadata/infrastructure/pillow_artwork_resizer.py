"""Pillow implementation of ``ArtworkResizerPort`` (ADR-034).

Follows the ``LocalAvatarStorage`` pattern: the CPU-bound decode +
resample runs in a worker thread, the decoded format (not a declared
MIME) decides whether the bytes are accepted, and the pixels are
force-loaded so a truncated file fails here rather than mid-encode.
Unlike avatars, variants keep the source format — a JPEG backdrop
stays JPEG, a PNG logo keeps its alpha channel — so the served
``Content-Type`` still follows the key's extension.
"""

from __future__ import annotations

import asyncio
import io
import sys

from PIL import Image, ImageOps, UnidentifiedImageError

from src.modules.metadata.application.ports.artwork_resizer_port import (
    ArtworkResizerPort,
    ResizedArtwork,
    UnsupportedArtworkImageError,
)

# Pillow format names we will re-encode. Animated GIF and AVIF (which
# needs a plugin) are refused so the original is served instead.
_RESIZABLE_FORMATS = frozenset({"JPEG", "PNG", "WEBP"})

_FORMAT_CONTENT_TYPES = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
}

# JPEG cannot carry alpha or CMYK; anything else is converted to RGB.
_JPEG_MODES = frozenset({"RGB", "L"})

# Encoder quality for lossy outputs — visually lossless for catalog art
# at these widths, well under the provider's own encoding size.
_JPEG_QUALITY = 85
_WEBP_QUALITY = 85


class PillowArtworkResizer(ArtworkResizerPort):
    """Downscale artwork with Pillow's LANCZOS resampler, off the event loop."""

    async def resize(self, content: bytes, *, width: int) -> ResizedArtwork | None:
        """See :meth:`ArtworkResizerPort.resize`."""
        return await asyncio.to_thread(self._resize_sync, content, width)

    @staticmethod
    def _resize_sync(content: bytes, width: int) -> ResizedArtwork | None:
        """Synchronous Pillow work — open, validate, orient, scale, encode."""
        try:
            with Image.open(io.BytesIO(content)) as source:
                image_format = source.format
                if image_format not in _RESIZABLE_FORMATS:
                    raise UnsupportedArtworkImageError(
                        f"image format {image_format!r} is not resizable"
                    )
                source.load()
                # Bake the EXIF orientation in: the variant drops the
                # tag, so without this a rotated photo would render
                # sideways next to its correctly displayed original.
                image = ImageOps.exif_transpose(source) or source
                if image.width <= width:
                    return None
                image.thumbnail((width, sys.maxsize), Image.Resampling.LANCZOS)
                return _encode(image, image_format)
        except (UnidentifiedImageError, Image.DecompressionBombError, OSError) as exc:
            raise UnsupportedArtworkImageError(
                "artwork bytes did not decode as a resizable image"
            ) from exc


def _encode(image: Image.Image, image_format: str) -> ResizedArtwork:
    """Re-encode ``image`` in its source format."""
    buffer = io.BytesIO()
    if image_format == "JPEG":
        if image.mode not in _JPEG_MODES:
            image = image.convert("RGB")
        image.save(buffer, format="JPEG", quality=_JPEG_QUALITY, optimize=True, progressive=True)
    elif image_format == "PNG":
        image.save(buffer, format="PNG", optimize=True)
    else:
        image.save(buffer, format="WEBP", quality=_WEBP_QUALITY)
    return ResizedArtwork(
        content=buffer.getvalue(),
        content_type=_FORMAT_CONTENT_TYPES[image_format],
        width=image.width,
    )


__all__ = ["PillowArtworkResizer"]
