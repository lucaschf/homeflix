"""Read-only proxy that serves mirrored catalog artwork (ADR-029).

The catalog stores a relative ``/api/v1/artwork/{key}`` URL once an
image has been mirrored into storage. This route reads the object
back through :class:`ArtworkStoragePort` and streams it to the
client, so the browser never talks to the storage backend directly.

When the object is not in storage (mirror hasn't run yet, or the key
is unknown) the route degrades gracefully: if a remote origin URL was
supplied it redirects there, otherwise 404. That keeps the catalog
functional while the background mirror job is still catching up.
"""

from typing import Annotated
from urllib.parse import urlsplit

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse, Response

from src.config.containers import ApplicationContainer
from src.modules.metadata.application.ports.artwork_downloader_port import ALLOWED_ARTWORK_HOSTS
from src.modules.metadata.application.ports.artwork_storage_port import ArtworkStoragePort
from src.modules.metadata.domain.value_objects.artwork_key import ARTWORK_KEY_PATTERN

router = APIRouter(prefix="/api/v1/artwork", tags=["Artwork"])

# Key charset is defined once on ``ArtworkKey`` (the write path) and
# reused here for the read path. The charset admits dots, so an all-dots
# key (``.``/``..``) is rejected separately below — it is not a valid
# object and would otherwise reach the storage adapter as a directory /
# traversal-shaped path.

# Cache mirrored art aggressively — a content-hashed key is immutable,
# so a long-lived immutable cache is safe and spares the proxy on every
# repeat view.
_CACHE_CONTROL = "public, max-age=31536000, immutable"


def _is_allowed_origin(origin: str) -> bool:
    """Whether ``origin`` is an https URL on an allow-listed provider host.

    Reuses ``ALLOWED_ARTWORK_HOSTS`` (the same set the downloader fetches
    from) so the redirect fallback can only bounce to a real provider
    CDN — the public endpoint is never an open redirect.
    """
    parts = urlsplit(origin)
    return parts.scheme == "https" and parts.hostname in ALLOWED_ARTWORK_HOSTS


@router.get("/{key}")
@inject
async def get_artwork(
    key: str,
    origin: Annotated[
        str | None,
        Query(description="Remote origin URL to fall back to when not yet mirrored"),
    ] = None,
    storage: ArtworkStoragePort = Depends(
        Provide[ApplicationContainer.metadata.artwork_storage],
    ),
) -> Response:
    """Serve a mirrored artwork object, or fall back to its origin.

    Not auth-gated: artwork is public catalog imagery embedded in
    pages and ``<img>`` tags that cannot carry auth headers, mirroring
    how the TMDB URLs were served before. Path traversal is blocked by
    the key charset + all-dots check; the ``origin`` fallback only
    redirects to allow-listed provider hosts (no open redirect).
    """
    if not ARTWORK_KEY_PATTERN.match(key) or set(key) <= {"."}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="invalid artwork key",
        )

    stored = await storage.open(key)
    if stored is None:
        # Not mirrored yet — bounce the client to the provider so the
        # image still renders while the job catches up, but only when the
        # origin is an allow-listed provider host (else behave as a miss).
        if origin and _is_allowed_origin(origin):
            return RedirectResponse(url=origin, status_code=status.HTTP_302_FOUND)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="artwork not found",
        )

    return Response(
        content=stored.content,
        media_type=stored.content_type,
        headers={
            "Cache-Control": _CACHE_CONTROL,
            # Never let the browser MIME-sniff a stored object into an
            # executable type (defense-in-depth against a mis-typed asset).
            "X-Content-Type-Options": "nosniff",
        },
    )


__all__ = ["router"]
