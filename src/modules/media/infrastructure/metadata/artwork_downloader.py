"""httpx implementation of ``ArtworkDownloaderPort`` (ADR-029).

Streams the response and aborts as soon as the accumulated body would
exceed ``max_bytes``, so a mis-sized or hostile URL can never buffer an
unbounded payload into memory. Transport failures are translated into
the shared gateway exception hierarchy, mirroring ``TmdbClient``'s
error handling so the mirror job sees one exception family.
"""

from __future__ import annotations

import httpx

from src.building_blocks.infrastructure.errors import (
    GatewayBadResponseException,
    GatewayTimeoutException,
    GatewayUnavailableException,
)
from src.config.logging import get_logger
from src.modules.media.application.ports.artwork_downloader_port import (
    ArtworkDownloaderPort,
    DownloadedImage,
)

_logger = get_logger()

_GATEWAY_NAME = "artwork-cdn"
_DEFAULT_CONTENT_TYPE = "application/octet-stream"


class HttpxArtworkDownloader(ArtworkDownloaderPort):
    """Download artwork bytes over HTTP with a hard size ceiling.

    Owns a single long-lived ``httpx.AsyncClient`` (thread-safe, pooled),
    constructed with ``follow_redirects=True`` because provider image
    CDNs commonly 30x to a resized variant.

    Args:
        timeout_seconds: Per-request timeout. Defaults to 30s, matching
            the metadata client.
    """

    def __init__(self, *, timeout_seconds: float = 30.0) -> None:
        self._client = httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=True)

    async def fetch(self, url: str, *, max_bytes: int) -> DownloadedImage:
        """Stream ``url`` into memory, aborting past ``max_bytes``."""
        try:
            async with self._client.stream("GET", url) as response:
                response.raise_for_status()
                content = await self._read_capped(response, max_bytes, url)
                content_type = response.headers.get("content-type", _DEFAULT_CONTENT_TYPE)
                return DownloadedImage(content=content, content_type=content_type)
        except httpx.TimeoutException as exc:
            raise GatewayTimeoutException(
                message="Artwork download timed out",
                gateway_name=_GATEWAY_NAME,
                internal_message=f"Timeout fetching {url}",
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise GatewayBadResponseException(
                message="Artwork provider returned an error status",
                gateway_name=_GATEWAY_NAME,
                internal_message=f"HTTP {exc.response.status_code} fetching {url}",
            ) from exc
        except httpx.HTTPError as exc:
            raise GatewayUnavailableException(
                message="Artwork provider is unavailable",
                gateway_name=_GATEWAY_NAME,
                internal_message=f"Transport error fetching {url}: {exc}",
            ) from exc

    async def _read_capped(
        self,
        response: httpx.Response,
        max_bytes: int,
        url: str,
    ) -> bytes:
        """Accumulate the streamed body, raising once it passes the cap."""
        buffer = bytearray()
        async for chunk in response.aiter_bytes():
            buffer.extend(chunk)
            if len(buffer) > max_bytes:
                raise GatewayBadResponseException(
                    message="Artwork exceeds the maximum allowed size",
                    gateway_name=_GATEWAY_NAME,
                    internal_message=f"Body over {max_bytes} bytes fetching {url}",
                )
        return bytes(buffer)

    async def aclose(self) -> None:
        """Close the underlying client (called on app shutdown)."""
        await self._client.aclose()


__all__ = ["HttpxArtworkDownloader"]
