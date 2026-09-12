"""Content-visibility policy shared across bounded contexts (ADR-035).

Normalization of certification labels to a comparable age
(:func:`classify`) and the rule that decides what a profile may see
(:class:`ViewingPolicy`) live in the shared kernel because four
contexts reason about them: ``media`` projects the policy into catalog
queries, ``identity`` owns the profile that carries the limit, and
``collections`` and ``watch_progress`` filter their own projections
through the same rule (ADR-018 admission criterion).
"""

from src.shared_kernel.content_policy.certification_scale import (
    BR_DEJUS_SCALE,
    UNRATED_LABELS,
    US_MPA_SCALE,
    US_TV_SCALE,
    classify,
    strictest,
)
from src.shared_kernel.content_policy.viewing_policy import ViewingPolicy

__all__ = [
    "BR_DEJUS_SCALE",
    "UNRATED_LABELS",
    "US_MPA_SCALE",
    "US_TV_SCALE",
    "ViewingPolicy",
    "classify",
    "strictest",
]
