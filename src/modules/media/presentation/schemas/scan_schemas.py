"""Pydantic schemas for media scan endpoints."""

from pydantic import BaseModel, Field


class ScanMediaRequest(BaseModel):
    """Request body for triggering a media scan.

    Every scan now belongs to a specific library — the catalog
    persists the owning ``library_id`` per Movie / Series so reads
    can be filtered per-profile downstream. Manual scans must
    therefore name a library; the route loads its configured paths
    and forwards them to the scan use case.
    """

    library_id: str = Field(
        ...,
        description="External id (lib_xxx) of the library to scan.",
    )


__all__ = ["ScanMediaRequest"]
