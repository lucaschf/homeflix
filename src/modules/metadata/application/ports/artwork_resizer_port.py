"""Port for downscaling a stored artwork image (ADR-034).

The adapter only reports facts about the bytes it is given — it never
decides what to serve. ``resize`` returns the smaller rendition, or
``None`` when the source is not wider than the requested width (the
caller then serves the original rather than an upscale), and raises
:class:`UnsupportedArtworkImageError` when the bytes cannot be decoded
as a resizable raster image. What to do in either case is the
:class:`ArtworkVariantService`'s policy.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


class UnsupportedArtworkImageError(Exception):
    """Raised when the bytes do not decode as a resizable raster image.

    Covers corrupt or truncated files, animated/vector formats the
    adapter refuses, and decompression-bomb rejections — anything where
    a variant cannot be derived and the original should be served as-is.
    """


@dataclass(frozen=True, slots=True)
class ResizedArtwork:
    """One downscaled rendition of an artwork image.

    Attributes:
        content: Encoded image bytes in the source's own format.
        content_type: MIME type of ``content`` (``image/jpeg`` etc.).
        width: Actual pixel width of the rendition.
    """

    content: bytes
    content_type: str
    width: int


class ArtworkResizerPort(ABC):
    """Downscale artwork bytes to a target width, keeping aspect and format."""

    @abstractmethod
    async def resize(self, content: bytes, *, width: int) -> ResizedArtwork | None:
        """Return ``content`` scaled down to ``width`` pixels wide.

        Args:
            content: Encoded source image bytes.
            width: Target width in pixels; the height follows the aspect ratio.

        Returns:
            The rendition, or ``None`` when the source is already
            ``width`` pixels wide or narrower (never upscales).

        Raises:
            UnsupportedArtworkImageError: When the bytes are not a
                decodable, resizable raster image.
        """
        ...


__all__ = ["ArtworkResizerPort", "ResizedArtwork", "UnsupportedArtworkImageError"]
