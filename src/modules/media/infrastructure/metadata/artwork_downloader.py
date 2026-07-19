"""httpx implementation of ``ArtworkDownloaderPort`` (ADR-029).

Streams the response and aborts as soon as the accumulated body would
exceed ``max_bytes``, so a mis-sized or hostile URL can never buffer an
unbounded payload into memory. Transport failures are translated into
the shared gateway exception hierarchy, mirroring ``TmdbClient``'s
error handling so the mirror job sees one exception family.

Because the URLs come from the database (a server-side fetch), the
target is constrained to ``https`` on an allow-listed provider host and
redirects are NOT followed — an unconstrained fetch of a DB-controlled
URL would be an SSRF primitive.
"""

from __future__ import annotations

from urllib.parse import urlsplit

import httpx

from src.building_blocks.infrastructure.errors import (
    GatewayBadResponseException,
    GatewayTimeoutException,
    GatewayUnavailableException,
)
from src.config.logging import get_logger
from src.modules.media.application.ports.artwork_downloader_port import (
    ALLOWED_ARTWORK_HOSTS,
    ArtworkDownloaderPort,
    DownloadedImage,
)

_logger = get_logger()

_GATEWAY_NAME = "artwork-cdn"


class HttpxArtworkDownloader(ArtworkDownloaderPort):
    """Download artwork bytes over HTTP with a hard size ceiling.

    Owns a single long-lived ``httpx.AsyncClient`` (thread-safe, pooled),
    with ``follow_redirects=False`` so a 30x cannot bounce the fetch to an
    internal target (provider image URLs are direct 200s).

    Args:
        timeout_seconds: Per-request timeout. Defaults to 30s, matching
            the metadata client.
        client: Optional injected client (tests pass a fake). Defaults to
            a redirect-disabled ``httpx.AsyncClient``.
    """

    def __init__(
        self,
        *,
        timeout_seconds: float = 30.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._client = client or httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=False)

    async def fetch(self, url: str, *, max_bytes: int) -> DownloadedImage:
        """Stream ``url`` into memory, aborting past ``max_bytes``.

        The URL must be ``https`` on an allow-listed provider host, else
        it is rejected before any request is made (SSRF guard).
        """
        self._reject_disallowed(url)
        try:
            async with self._client.stream("GET", url) as response:
                response.raise_for_status()
                if response.is_redirect:
                    # Redirects are disabled; a 3xx here means the CDN
                    # tried to bounce us — refuse rather than store the
                    # redirect body or chase the target.
                    raise GatewayBadResponseException(
                        message="Artwork provider attempted a redirect",
                        gateway_name=_GATEWAY_NAME,
                        internal_message=f"Unexpected {response.status_code} redirect for {url}",
                    )
                content = await self._read_capped(response, max_bytes, url)
                content_type = response.headers.get("content-type")
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

    def _reject_disallowed(self, url: str) -> None:
        """Raise unless ``url`` is https on an allow-listed provider host."""
        parts = urlsplit(url)
        if parts.scheme != "https" or parts.hostname not in ALLOWED_ARTWORK_HOSTS:
            raise GatewayBadResponseException(
                message="Artwork URL is not an allowed provider host",
                gateway_name=_GATEWAY_NAME,
                internal_message=f"Refusing to fetch disallowed URL {url}",
            )

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
        """Close the underlying httpx client.

        Not wired to a shutdown hook today (the singleton's sockets are
        reclaimed at process exit); provided so a future
        ``providers.Resource`` finalizer, or a test, can close it
        deterministically.
        """
        await self._client.aclose()


__all__ = ["HttpxArtworkDownloader"]
