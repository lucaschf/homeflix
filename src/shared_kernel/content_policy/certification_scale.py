"""Normalization of certification labels to a comparable minimum age (ADR-035).

The table lives in the domain, not in the provider adapter: which age a
label means is a policy of the business, and an adapter that decided it
would be deciding instead of translating. The adapter's job is to hand
over the country and the verbatim label; :func:`classify` turns that
into a :class:`Certification`.
"""

import re
from types import MappingProxyType
from typing import Final

from src.shared_kernel.value_objects.age_rating import AgeRating
from src.shared_kernel.value_objects.certification import Certification
from src.shared_kernel.value_objects.content_rating import ContentRating
from src.shared_kernel.value_objects.rating_system import RatingSystem

# Brazilian Classificação Indicativa. The ``A``-prefixed spellings
# ("AL", "A12") are how the labels are rendered in players and how an
# operator is likely to type them; TMDB emits the bare forms.
BR_DEJUS_SCALE: Final[MappingProxyType[str, int]] = MappingProxyType(
    {
        "L": 0,
        "AL": 0,
        "LIVRE": 0,
        "10": 10,
        "A10": 10,
        "12": 12,
        "A12": 12,
        "14": 14,
        "A14": 14,
        "16": 16,
        "A16": 16,
        "18": 18,
        "A18": 18,
    }
)

# Motion Picture Association film ratings.
#
# ``PG`` maps to 13, not to 10 or 8: half of the PG titles in a typical
# library predate 1984, when PG-13 did not exist and PG absorbed
# everything that would carry PG-13 today — including horror. In
# parental control, permitting wrongly is the failure that matters, so
# the ambiguous label takes the stricter reading. ``system`` is
# persisted precisely so this can be refined by release year later
# without re-deriving every row (ADR-035, decision 2).
US_MPA_SCALE: Final[MappingProxyType[str, int]] = MappingProxyType(
    {
        "G": 0,
        "PG": 13,
        "PG-13": 13,
        "PG13": 13,
        "R": 17,
        "NC-17": 18,
        "NC17": 18,
    }
)

# US television parental guidelines.
US_TV_SCALE: Final[MappingProxyType[str, int]] = MappingProxyType(
    {
        "TV-Y": 0,
        "TV-Y7": 7,
        "TV-Y7-FV": 7,
        "TV-G": 0,
        "TV-PG": 10,
        "TV-14": 14,
        "TV-MA": 17,
    }
)

# Labels that explicitly assert the absence of a rating. Recognized so
# they are not mistaken for an unknown scale, but they still yield no
# age: callers resolve that through ``AgeRating.allows``.
UNRATED_LABELS: Final[frozenset[str]] = frozenset(
    {"NR", "UR", "N/A", "NA", "NOT RATED", "UNRATED", "NONE", "-"}
)

# A label that already is the minimum age: "6", "12", "16+", "0+".
_NUMERIC_LABEL: Final[re.Pattern[str]] = re.compile(r"^(\d{1,2})\+?$")

_SYSTEM_BY_COUNTRY: Final[MappingProxyType[str, tuple[RatingSystem, ...]]] = MappingProxyType(
    {
        "BR": (RatingSystem.BR_DEJUS,),
        "US": (RatingSystem.US_MPA, RatingSystem.US_TV),
    }
)

_SCALES: Final[MappingProxyType[RatingSystem, MappingProxyType[str, int]]] = MappingProxyType(
    {
        RatingSystem.BR_DEJUS: BR_DEJUS_SCALE,
        RatingSystem.US_MPA: US_MPA_SCALE,
        RatingSystem.US_TV: US_TV_SCALE,
    }
)

# Order used when no country is known.
_LOOKUP_ORDER: Final[tuple[RatingSystem, ...]] = (
    RatingSystem.US_MPA,
    RatingSystem.US_TV,
    RatingSystem.BR_DEJUS,
)

# Without a country, a scale contributes only the labels that identify
# it on sight. Brazil's bare numerals ("12") are shared with every
# European board, so attributing them to Brazil would be a guess; they
# fall through to the generic numeric scale instead, which yields the
# same age and claims less. The "A"-prefixed and word spellings stay,
# being unambiguous.
_UNHINTED_SCALES: Final[
    MappingProxyType[RatingSystem, MappingProxyType[str, int]]
] = MappingProxyType(
    {
        system: MappingProxyType(
            {label: age for label, age in scale.items() if not _NUMERIC_LABEL.match(label)}
        )
        for system, scale in _SCALES.items()
    }
)


def _canonical(raw: str) -> str:
    """Upper-case, trim, and collapse internal whitespace."""
    return " ".join(raw.split()).upper()


def _numeric_age(token: str) -> int | None:
    """Read a label that is already an age, clamped to the scale's ceiling.

    A nonsensical number ("99") clamps to :attr:`AgeRating.MAX` rather
    than being discarded: a discarded label resolves to adult (18),
    which would be *less* restrictive than what the label claims.
    """
    match = _NUMERIC_LABEL.match(token)
    if match is None:
        return None
    return min(int(match.group(1)), AgeRating.MAX)


def classify(label: str | ContentRating, *, country: str | None = None) -> Certification:
    """Normalize a provider's certification label into a :class:`Certification`.

    Never raises on an unrecognized label and never guesses an age it
    cannot support: an unknown or explicitly-unrated label comes back
    with ``minimum_age`` unset, which every consumer resolves to adult
    through :meth:`AgeRating.allows`. Callers that want an operator to
    notice (metadata enrichment, for one) log the undetermined case —
    the domain reports the fact, it does not decide what to do about it.

    Args:
        label: The certification exactly as the provider emitted it.
        country: ISO 3166-1 alpha-2 code of the jurisdiction the label
            came from, when known. Only disambiguates — a label found
            in another scale is still recognized without it. Its one
            real effect is attributing a bare number: ``"12"`` from
            ``BR`` is Classificação Indicativa, and from nowhere in
            particular is the generic numeric scale.

    Returns:
        The label paired with its scale and, when derivable, its
        minimum age.

    Example:
        >>> classify("PG-13").minimum_age.value
        13
        >>> classify("12", country="BR").system
        <RatingSystem.BR_DEJUS: 'br_dejus'>
        >>> classify("NR").is_determined
        False
        >>> classify("16+").minimum_age.value
        16
    """
    original = label.value if isinstance(label, ContentRating) else label
    content_rating = label if isinstance(label, ContentRating) else ContentRating(label)
    token = _canonical(original)

    if token in UNRATED_LABELS:
        return Certification.undetermined(content_rating)

    preferred = _SYSTEM_BY_COUNTRY.get((country or "").strip().upper(), ())
    candidates = [(system, _SCALES[system]) for system in preferred]
    candidates += [(system, _UNHINTED_SCALES[system]) for system in _LOOKUP_ORDER]

    for system, scale in candidates:
        age = scale.get(token)
        if age is not None:
            return Certification(
                system=system,
                label=content_rating,
                minimum_age=AgeRating(age),
            )

    numeric = _numeric_age(token)
    if numeric is not None:
        return Certification(
            system=RatingSystem.NUMERIC,
            label=content_rating,
            minimum_age=AgeRating(numeric),
        )

    return Certification.undetermined(content_rating)


def strictest(
    certifications: "list[Certification] | tuple[Certification, ...]",
) -> Certification | None:
    """Return the most restrictive certification that yields an age.

    The tie-breaker for a title carrying labels from several
    jurisdictions, and the fallback when no preferred jurisdiction has
    one (ADR-035, decision 10). Certifications without a determinable
    age are ignored rather than treated as adult: they carry no
    information to be strict about, and letting them win would mask
    every real label the title has.

    Args:
        certifications: Candidates, in any order.

    Returns:
        The candidate with the highest minimum age, or ``None`` when
        none of them has one.
    """
    determined = [c for c in certifications if c.minimum_age is not None]
    if not determined:
        return None
    return max(determined, key=lambda c: c.minimum_age.value)  # type: ignore[union-attr]


__all__ = [
    "BR_DEJUS_SCALE",
    "UNRATED_LABELS",
    "US_MPA_SCALE",
    "US_TV_SCALE",
    "classify",
    "strictest",
]
