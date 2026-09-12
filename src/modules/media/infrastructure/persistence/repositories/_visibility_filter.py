"""The one place a catalog query may mention ``library_id`` or ``minimum_age``.

``ViewingPolicy.permits()`` is the definition of catalog visibility; what
this module builds is its **projection** into SQL (ADR-017, ADR-035 §7).
Keeping every predicate here is what makes the two testable against each
other, and what lets an architecture test assert that no repository grows
a second, subtly different copy of the rule — which is exactly how
``watch_progress`` and the watchlist ended up with no ACL at all.

The filter has to run in SQL, not after the query. Three read paths merge
two streams in Python — genre browse, search, recently-added — and each
of them applies ``LIMIT`` before any Python-side filter could run, so
filtering afterwards either re-serves rows (the genre cursor is
positional) or silently shortens the page with no signal that content
was missing.
"""

from collections.abc import Sequence

from sqlalchemy import and_, false, or_
from sqlalchemy.sql.elements import ColumnElement

from src.modules.media.infrastructure.persistence.models.movie import MovieModel
from src.modules.media.infrastructure.persistence.models.series import SeriesModel
from src.shared_kernel.content_policy import ViewingPolicy
from src.shared_kernel.value_objects.age_rating import AgeRating
from src.shared_kernel.value_objects.library_id import LibraryId

type CatalogModel = type[MovieModel] | type[SeriesModel]
"""The models that carry both visibility axes.

``EpisodeModel`` and ``SeasonModel`` carry neither: they are scoped
through their parent ``Series``, which is why a restricted series is
hidden whole rather than per episode (ADR-035, known limitations).
Spelling the union out makes mypy reject the wrong model at the call
site instead of producing invalid SQL at runtime.
"""


def visibility_conditions(
    model: CatalogModel,
    policy: ViewingPolicy | None,
) -> list[ColumnElement[bool]]:
    """Build the WHERE clauses that project ``ViewingPolicy.permits()``.

    Args:
        model: The catalog model being queried.
        policy: The caller's viewing policy, or ``None`` for an
            internal read that is not profile-scoped at all — the
            scanner, background jobs, and the reload a ``save`` does.
            ``None`` means *no gate*, which is why it must stay an
            explicit choice at every call site rather than a default.

    Returns:
        Conditions to splat into a ``where()``. Empty when ungated.

    Example:
        >>> conditions = visibility_conditions(MovieModel, policy)
        >>> stmt = select(MovieModel).where(*conditions)
    """
    if policy is None:
        return []

    if policy.denies_everything:
        # An empty ACL is deny-all (ADR-018 §3). Rendering ``0 = 1``
        # keeps the shape of the query intact — counts, cursors and
        # ``has_more`` all stay consistent — instead of making every
        # caller remember to short-circuit.
        return [false()]

    conditions: list[ColumnElement[bool]] = [
        model.library_id.in_([library_id.value for library_id in policy.allowed_library_ids])
    ]

    limit = policy.maturity_limit
    if limit is None:
        # ``permits_maturity`` is unconditionally True, so emitting an
        # age clause here would only risk diverging from the domain.
        return conditions

    # A row counts as classified only when it carries a label. The
    # mapper decides this by truthiness, not by NULL
    # (``_certification.py``: ``if not model.content_rating: return
    # None``), so the projection tests the same way — otherwise a row
    # with an empty label and an age would pass the SQL and be denied
    # by the domain, which is fail-open in a parental gate.
    labelled = and_(model.content_rating.is_not(None), model.content_rating != "")
    classified = and_(model.minimum_age <= limit.value, labelled)

    if limit.value >= AgeRating.ADULT:
        # ``AgeRating.allows(None)`` resolves an undeterminable rating
        # to ADULT, so those rows become visible exactly here and not
        # one rung earlier. "Undeterminable" has three shapes in the
        # table because the mapper reads the label first.
        unclassified = or_(
            model.minimum_age.is_(None),
            model.content_rating.is_(None),
            model.content_rating == "",
        )
        conditions.append(or_(classified, unclassified))
    else:
        # Below ADULT no unclassified row may pass, and a NULL age
        # already fails ``<=`` on its own.
        conditions.append(classified)

    return conditions


def library_scope_condition(model: CatalogModel, library_id: str) -> ColumnElement[bool]:
    """Scope a query to one library — an operator filter, not a gate.

    This is the admin's "show me library X" query param, which narrows
    within what the caller may already see. It lives here so the
    architecture rule can be absolute: no predicate over ``library_id``
    or ``minimum_age`` is written anywhere else in the catalog
    repositories, with no allowlist of exceptions.

    Args:
        model: The catalog model being queried.
        library_id: Raw ``lib_xxx`` value from the request.

    Returns:
        The equality condition.
    """
    return model.library_id == library_id


def library_acl_conditions(
    model: CatalogModel,
    allowed_library_ids: Sequence[LibraryId] | None,
) -> list[ColumnElement[bool]]:
    """Restrict an operator worklist by library — a filter, not a viewing gate.

    Backs the admin enrichment-review queue, which must **never** apply
    the maturity axis: hiding titles by age would keep from the operator
    exactly the rows that still need classifying, and manual
    classification is the correction valve for the label-to-age table
    (ADR-035). Catalog reads that a profile browses go through
    :func:`visibility_conditions` instead. This lives here only so that
    no ``library_id`` predicate is written anywhere else in the catalog
    repositories.

    Args:
        model: The catalog model being queried.
        allowed_library_ids: Libraries the listing is restricted to, or
            ``None`` for no library filter. Empty means nothing matches.

    Returns:
        Conditions to splat into a ``where()``. Empty when unfiltered.
    """
    if allowed_library_ids is None:
        return []

    allowed = [library_id.value for library_id in allowed_library_ids]
    if not allowed:
        return [false()]

    return [model.library_id.in_(allowed)]


__all__ = [
    "CatalogModel",
    "library_acl_conditions",
    "library_scope_condition",
    "visibility_conditions",
]
