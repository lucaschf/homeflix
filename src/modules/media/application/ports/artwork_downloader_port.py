"""Port for downloading provider artwork bytes (ADR-029).

The mirror job needs the raw bytes of a remote poster/backdrop/logo so
it can persist them via :class:`ArtworkStoragePort`. Fetching over HTTP
is infrastructure; the job talks to this port and an adapter under
``media/infrastructure/`` owns the HTTP client. Keeping it behind a
port lets the job be tested with an in-memory fake and keeps transport
concerns out of the orchestration.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

#: Provider image hosts artwork may be downloaded from (and, in the read
#: route, redirected to). Downloading is a server-side fetch of a
#: DB-stored URL, so it MUST be constrained to known provider CDNs — an
#: unconstrained fetch is an SSRF primitive. TMDB is the only image
#: provider today; extend as providers are added. Shared by the
#: downloader adapter (write path) and the proxy route (redirect path).
ALLOWED_ARTWORK_HOSTS = frozenset({"image.tmdb.org"})


@dataclass(frozen=True, slots=True)
class DownloadedImage:
    """Bytes plus content type of a fetched image.

    Attributes:
        content: The raw image bytes.
        content_type: The response ``Content-Type`` (e.g. ``image/jpeg``)
            exactly as the provider sent it, or ``None`` when the header
            was absent — the caller decides how to treat a missing type
            rather than the adapter fabricating one.
    """

    content: bytes
    content_type: str | None


class ArtworkDownloaderPort(ABC):
    """Fetch the bytes of a remote artwork URL."""

    @abstractmethod
    async def fetch(self, url: str, *, max_bytes: int) -> DownloadedImage:
        """Download the image at ``url``.

        Args:
            url: Absolute http(s) URL of the provider image.
            max_bytes: Hard ceiling on the response body. The adapter
                MUST abort (raising) rather than buffer a larger payload,
                so a mis-sized or hostile URL cannot exhaust memory.

        Returns:
            The downloaded bytes and content type.

        Raises:
            GatewayException: On timeout, transport error, non-2xx
                status, or a body exceeding ``max_bytes``. The caller
                (mirror job) catches these and leaves the remote URL in
                place, retrying on a later tick.
        """
        ...


__all__ = ["ArtworkDownloaderPort", "DownloadedImage"]
