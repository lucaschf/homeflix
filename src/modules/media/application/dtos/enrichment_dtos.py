"""DTOs for metadata enrichment operations."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class EnrichMediaInput:
    """Input for enriching a single media item.

    Attributes:
        media_id: External ID of the movie or series.
        force: Re-enrich even if metadata already exists.
    """

    media_id: str
    force: bool = False


@dataclass(frozen=True)
class EnrichMediaOutput:
    """Output of a single media enrichment.

    Attributes:
        media_id: External ID of the enriched item.
        enriched: Whether metadata was applied.
        provider: Name of the provider that supplied metadata.
        error: Error message if enrichment failed.
    """

    media_id: str
    enriched: bool
    provider: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class BulkEnrichInput:
    """Input for bulk metadata enrichment.

    Attributes:
        force: Re-enrich even if metadata already exists.
    """

    force: bool = False


@dataclass(frozen=True)
class BulkEnrichOutput:
    """Output of bulk metadata enrichment.

    Attributes:
        movies_enriched: Number of movies successfully enriched.
        series_enriched: Number of series successfully enriched.
        skipped: Number of items skipped (already enriched).
        errors: List of error messages.
    """

    movies_enriched: int
    series_enriched: int
    skipped: int
    errors: list[str] = field(default_factory=list)


__all__ = [
    "BulkEnrichInput",
    "BulkEnrichOutput",
    "EnrichMediaInput",
    "EnrichMediaOutput",
]
