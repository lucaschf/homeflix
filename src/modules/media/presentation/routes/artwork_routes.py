"""Read-only proxy that serves mirrored catalog artwork (ADR-029).

The catalog stores a relative ``/api/v1/artwork/{key}`` URL once an
image has been mirrored into object storage. This route reads the
object back through :class:`ArtworkStoragePort` and streams it to the
client, so the browser never talks to the storage backend directly.

When the object is not in storage (mirror hasn't run yet, or the key
is unknown) the route degrades gracefully: if a remote origin URL was
supplied it redirects there, otherwise 404. That keeps the catalog
functional while the background mirror job is still catching up.
"""

import re
from typing import Annotated

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse, Response

from src.config.containers import ApplicationContainer
from src.modules.media.application.ports.artwork_storage_port import ArtworkStoragePort

router = APIRouter(prefix="/api/v1/artwork", tags=["Artwork"])

# Keys are derived server-side (content hash + extension) and embedded
# verbatim in the path. Reject anything outside the safe charset so a
# crafted key can never escape the bucket namespace or the path param.
_KEY_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")

# Cache mirrored art aggressively — a content-hashed key is immutable,
# so a long-lived immutable cache is safe and spares the proxy on every
# repeat view.
_CACHE_CONTROL = "public, max-age=31536000, immutable"


@router.get("/{key}")  # type: ignore[misc]
@inject  # type: ignore[misc]
async def get_artwork(
    key: str,
    origin: Annotated[
        str | None,
        Query(description="Remote origin URL to fall back to when not yet mirrored"),
    ] = None,
    storage: ArtworkStoragePort = Depends(
        Provide[ApplicationContainer.media.artwork_storage],
    ),
) -> Response:
    """Serve a mirrored artwork object, or fall back to its origin.

    Not auth-gated: artwork is public catalog imagery embedded in
    pages and ``<img>`` tags that cannot carry auth headers, mirroring
    how the TMDB URLs were served before. Path traversal is blocked by
    the key charset check.
    """
    if not _KEY_PATTERN.match(key):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="invalid artwork key",
        )

    stored = await storage.open(key)
    if stored is None:
        if origin:
            # Not mirrored yet — bounce the client to the provider so
            # the image still renders while the job catches up.
            return RedirectResponse(url=origin, status_code=status.HTTP_302_FOUND)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="artwork not found",
        )

    return Response(
        content=stored.content,
        media_type=stored.content_type,
        headers={"Cache-Control": _CACHE_CONTROL},
    )


__all__ = ["router"]
