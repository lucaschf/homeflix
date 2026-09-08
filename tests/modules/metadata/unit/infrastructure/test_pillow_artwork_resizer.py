"""Unit tests for :class:`PillowArtworkResizer` (ADR-034).

Real Pillow against images generated in memory — the point is the
encoder behaviour (format kept, alpha kept, EXIF orientation baked
in, no upscale), which a fake could not pin.
"""

from __future__ import annotations

import io

import pytest
from PIL import Image

from src.modules.metadata.application.ports.artwork_resizer_port import (
    UnsupportedArtworkImageError,
)
from src.modules.metadata.infrastructure.pillow_artwork_resizer import PillowArtworkResizer

_EXIF_ORIENTATION_TAG = 0x0112
_ROTATE_90_CW = 6


def _image(width: int, height: int, *, fmt: str, mode: str = "RGB", **save: object) -> bytes:
    color = (200, 30, 30, 128) if mode == "RGBA" else None
    buffer = io.BytesIO()
    Image.new(mode, (width, height), color).save(buffer, format=fmt, **save)  # type: ignore[arg-type]
    return buffer.getvalue()


def _decode(content: bytes) -> Image.Image:
    image = Image.open(io.BytesIO(content))
    image.load()
    return image


@pytest.fixture
def resizer() -> PillowArtworkResizer:
    return PillowArtworkResizer()


class TestResize:
    async def test_should_downscale_a_jpeg_keeping_aspect_and_format(
        self, resizer: PillowArtworkResizer
    ) -> None:
        result = await resizer.resize(_image(1600, 900, fmt="JPEG"), width=780)

        assert result is not None
        assert result.content_type == "image/jpeg"
        assert result.width == 780
        decoded = _decode(result.content)
        assert decoded.format == "JPEG"
        assert (decoded.width, decoded.height) in {(780, 438), (780, 439)}

    async def test_should_return_none_when_the_source_is_not_wider(
        self, resizer: PillowArtworkResizer
    ) -> None:
        assert await resizer.resize(_image(780, 439, fmt="JPEG"), width=780) is None
        assert await resizer.resize(_image(500, 750, fmt="JPEG"), width=780) is None

    async def test_should_keep_png_alpha(self, resizer: PillowArtworkResizer) -> None:
        result = await resizer.resize(_image(1000, 300, fmt="PNG", mode="RGBA"), width=500)

        assert result is not None
        assert result.content_type == "image/png"
        decoded = _decode(result.content)
        assert decoded.format == "PNG"
        assert decoded.mode == "RGBA"
        assert decoded.width == 500

    async def test_should_round_trip_webp(self, resizer: PillowArtworkResizer) -> None:
        result = await resizer.resize(_image(1200, 800, fmt="WEBP"), width=342)

        assert result is not None
        assert result.content_type == "image/webp"
        assert _decode(result.content).format == "WEBP"

    async def test_should_bake_the_exif_orientation_in(self, resizer: PillowArtworkResizer) -> None:
        exif = Image.Exif()
        exif[_EXIF_ORIENTATION_TAG] = _ROTATE_90_CW
        rotated = _image(1600, 900, fmt="JPEG", exif=exif.tobytes())

        result = await resizer.resize(rotated, width=780)

        # 1600x900 displayed rotated is 900x1600: the variant is portrait.
        assert result is not None
        decoded = _decode(result.content)
        assert decoded.width == 780
        assert decoded.height > decoded.width

    async def test_should_convert_cmyk_jpeg_to_rgb(self, resizer: PillowArtworkResizer) -> None:
        result = await resizer.resize(_image(1600, 900, fmt="JPEG", mode="CMYK"), width=780)

        assert result is not None
        assert _decode(result.content).mode == "RGB"

    async def test_should_reject_undecodable_bytes(self, resizer: PillowArtworkResizer) -> None:
        with pytest.raises(UnsupportedArtworkImageError):
            await resizer.resize(b"<html>rate limited</html>", width=780)

    async def test_should_reject_formats_it_will_not_re_encode(
        self, resizer: PillowArtworkResizer
    ) -> None:
        with pytest.raises(UnsupportedArtworkImageError):
            await resizer.resize(_image(1600, 900, fmt="GIF", mode="P"), width=780)

    async def test_should_reject_a_truncated_file(self, resizer: PillowArtworkResizer) -> None:
        whole = _image(1600, 900, fmt="PNG")

        with pytest.raises(UnsupportedArtworkImageError):
            await resizer.resize(whole[: len(whole) // 2], width=780)
