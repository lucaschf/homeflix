"""Scanner deduplication tunables — content-identity conflict detector."""

from pydantic import Field

from src.building_blocks.domain.value_objects import CompoundValueObject


class ScanDedupConfig(CompoundValueObject):
    """Operational knobs for the post-enrich conflict detector (ADR-015).

    Controls the runtime-delta heuristic that classifies a detected
    content-identity collision as either a likely same release or a
    suspected different edit (Director's Cut / Theatrical). A pair is
    only flagged as a suspected different edit when its runtime delta
    exceeds BOTH bounds — either alone is satisfied by routine
    encoding/cropping differences and would over-trigger.

    Attributes:
        runtime_delta_abs_minutes: Absolute runtime-delta ceiling, in
            minutes. Deltas at or below this are treated as the same
            release regardless of the relative bound.
        runtime_delta_relative: Relative runtime-delta ceiling as a
            fraction of the shorter runtime (``0.10`` = 10%). Deltas at
            or below this are treated as the same release regardless of
            the absolute bound.
        title_year_fallback_enabled: When ``True`` (default), the
            detector also flags duplicates by
            ``(normalized_original_title, year)`` — catching catalog
            entries whose enrichment never locked a TMDB id. Fallback
            matches always queue for the operator and are never
            silently auto-merged, since the identity is weaker.

    Example:
        >>> cfg = ScanDedupConfig()
        >>> stricter = cfg.with_updates(runtime_delta_abs_minutes=3.0)
    """

    runtime_delta_abs_minutes: float = Field(default=5.0, ge=0.0)
    runtime_delta_relative: float = Field(default=0.10, ge=0.0, le=1.0)
    title_year_fallback_enabled: bool = Field(default=True)


__all__ = ["ScanDedupConfig"]
