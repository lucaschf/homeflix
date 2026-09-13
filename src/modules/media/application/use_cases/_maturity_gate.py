"""Maturity check for the catalog detail use cases (ADR-035, decision 11)."""

from src.modules.media.application.errors import (
    ContentRestrictedByMaturityError,
    ContentRestrictedUnratedError,
)
from src.shared_kernel.content_policy import ViewingPolicy
from src.shared_kernel.value_objects.age_rating import AgeRating


def ensure_maturity_permits(policy: ViewingPolicy, minimum_age: AgeRating | None) -> None:
    """Raise when the policy's maturity axis denies a title already in reach.

    Only for a title fetched on the library axis alone: the library axis
    has already answered (and hides a title outside it as 404), so what is
    left to report is the age. ``ViewingPolicy.permits_maturity`` stays
    the definition of the rule; this only picks which error to surface.

    Args:
        policy: The caller's full viewing policy.
        minimum_age: The title's minimum age, or ``None`` when it has no
            determinable rating.

    Raises:
        ContentRestrictedUnratedError: If the title has no determinable
            rating and the policy's limit is below adult.
        ContentRestrictedByMaturityError: If the title is rated above the
            policy's limit.
    """
    limit = policy.maturity_limit
    if limit is None or policy.permits_maturity(minimum_age):
        return
    if minimum_age is None:
        raise ContentRestrictedUnratedError.for_limit(limit)
    raise ContentRestrictedByMaturityError.for_ages(required_age=minimum_age, profile_limit=limit)


__all__ = ["ensure_maturity_permits"]
