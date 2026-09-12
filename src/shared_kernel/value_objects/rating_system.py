"""Content-rating systems — the scales certification labels are written on (ADR-035)."""

from enum import StrEnum


class RatingSystem(StrEnum):
    """The classification scale a certification label belongs to.

    Persisted alongside the label rather than inferred at read time,
    because the same label means different things on different scales
    and in different eras (ADR-035, decision 2): the MPA's ``PG`` of
    1972 absorbed content that only got its own ``PG-13`` label in
    1984, so a title carrying ``PG`` cannot be placed on the age scale
    without knowing which system — and, later, which era — it came
    from.

    This enum names the **scale**, not the provenance of the value. Who
    supplied a rating (the metadata provider or an operator override)
    is a separate axis, tracked at persistence time.

    Attributes:
        BR_DEJUS: Brazilian Classificação Indicativa — L, 10, 12, 14,
            16, 18.
        US_MPA: Motion Picture Association film ratings — G, PG, PG-13,
            R, NC-17.
        US_TV: US television parental guidelines — TV-Y through TV-MA.
        NUMERIC: Scales whose label already *is* the minimum age
            (``6``, ``12``, ``15``, ``16+``), used by most European
            boards and as the fallback for a bare number of unknown
            origin.
        UNKNOWN: The label did not match any known scale, or is an
            explicit "not rated" marker. Carried so the original label
            still round-trips to the UI even though no age can be
            derived from it.

    Example:
        >>> RatingSystem.BR_DEJUS.value
        'br_dejus'
        >>> RatingSystem("us_mpa")
        <RatingSystem.US_MPA: 'us_mpa'>
    """

    BR_DEJUS = "br_dejus"
    US_MPA = "us_mpa"
    US_TV = "us_tv"
    NUMERIC = "numeric"
    UNKNOWN = "unknown"


__all__ = ["RatingSystem"]
