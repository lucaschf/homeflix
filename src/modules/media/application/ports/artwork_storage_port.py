"""Port for persisting catalog artwork outside the domain.

Poster / backdrop / logo / still images come from an external
metadata provider (TMDB) as remote URLs. Serving them straight from
``image.tmdb.org`` couples the catalog's availability to a third
party — a removed image, a rate limit, a CDN outage, or plain
offline use all make the art disappear (see ADR-029).

This port lets the application **mirror** those bytes into storage
the deployment controls. The use case talks to this port; the
adapter under ``media/infrastructure/storage/`` knows how to reach
the backing store — a local-disk directory by default, with an
S3 / MinIO adapter possible behind the same contract. The adapter
deliberately returns a **relative URL** (``/api/v1/artwork/{key}``)
rather than a store-specific URL so the domain and the frontend
never learn where the bytes actually live — swapping the backend is
an adapter change, invisible to callers (ADR-009 / ADR-025).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class StoredArtwork:
    """Bytes plus content type of a single stored artwork object.

    Returned by :meth:`ArtworkStoragePort.open` so the read-only
    proxy route can stream the object back with the right media type
    without the route knowing anything about the storage backend.

    Attributes:
        content: The raw image bytes as stored.
        content_type: The MIME type to serve them with (e.g.
            ``image/jpeg``). Persisted alongside the object at save
            time so the proxy never has to sniff it.
    """

    content: bytes
    content_type: str


class ArtworkStoragePort(ABC):
    """Persist, read back, or remove mirrored catalog artwork."""

    @abstractmethod
    async def save(self, *, content: bytes, content_type: str, key: str) -> str:
        """Store ``content`` under ``key`` and return its served URL.

        Args:
            content: Raw image bytes fetched from the provider.
            content_type: MIME type to persist and later serve with.
            key: Stable, storage-safe object key. Callers derive it
                deterministically (e.g. a content hash) so re-saving
                identical bytes is idempotent and de-duplicated. Must
                match ``[A-Za-z0-9._-]+`` — it is embedded verbatim in
                the served URL path.

        Returns:
            The relative URL the catalog should embed in place of the
            provider URL (e.g. ``/api/v1/artwork/ab12cd.jpg``).
            Returning a URL keeps the domain unaware of the backend.
        """
        ...

    @abstractmethod
    async def open(self, key: str) -> StoredArtwork | None:
        """Read the object back for the proxy route.

        Args:
            key: The object key previously returned via the served URL.

        Returns:
            The stored bytes and content type, or ``None`` when no
            object exists for ``key`` (the route turns that into a
            404 / remote-origin redirect).
        """
        ...

    @abstractmethod
    async def delete(self, key: str) -> None:
        """Remove the object for ``key``.

        Idempotent — a missing object is not an error, so callers can
        delete on every artwork change without a prior existence check.
        """
        ...


__all__ = ["ArtworkStoragePort", "StoredArtwork"]
