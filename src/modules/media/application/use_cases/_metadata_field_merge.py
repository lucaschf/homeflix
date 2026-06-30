"""Shared reconciliation of provider metadata into a media entity.

Both ``enrich_movie_metadata`` and ``enrich_series_metadata`` fold a bag of
provider fields onto the entity under a :class:`MergePolicy`. The pieces that
are identical between the two — the provider identity fields, the
"don't-overwrite" fill-if-empty fields shared by movie and series, the cast
conversion, and the localized overlay — live here once so a new shared field
is added in a single place instead of being hand-rolled in each use case
(which had drifted into two parallel implementations). The genuinely
divergent always-overwrite rules (movie title tracks TMDB while series title
is scanner-derived; ``year`` vs ``start_year``/``end_year``; the probed-
duration guard) stay explicit in each use case.

Per ADR-025, this reconciliation is an application/ACL concern: it consumes
provider port DTOs (:class:`MediaMetadata`) and translates them into domain
value objects. The domain owns the *policy* (:class:`MergePolicy`) and the
*invariants* (the entities validate on construction); this module owns the
field-by-field source-preference between stored and provider values.
"""

from collections.abc import Callable
from typing import Any

from src.modules.media.application.ports import MediaMetadata
from src.modules.media.application.use_cases._localized_metadata_helpers import (
    merge_media_localized,
)
from src.modules.media.domain.value_objects import (
    CastMember,
    ContentRating,
    Genre,
    ImageUrl,
    ImdbId,
    MergePolicy,
    Title,
    TmdbId,
)

# Fields shared by movie and series that are filled only when the entity left
# them empty (unless ``OVERWRITE``), keyed ``provider_attr: (entity_attr,
# converter)``. Each use case overlays its own type-specific entries on top
# (e.g. movie adds tagline / collection / directors / writers).
COMMON_FILL_IF_EMPTY: dict[str, tuple[str, Callable[[Any], Any] | None]] = {
    "synopsis": ("synopsis", None),
    "genres": ("genres", lambda v: [Genre(g) for g in v]),
    "poster_url": ("poster_path", ImageUrl),
    "backdrop_url": ("backdrop_path", ImageUrl),
    "logo_url": ("logo_path", ImageUrl),
    "content_rating": ("content_rating", ContentRating),
    "trailer_url": ("trailer_url", None),
}


def set_if_missing(
    updates: dict[str, object],
    metadata: MediaMetadata,
    entity: object,
    field_map: dict[str, tuple[str, Callable[[Any], Any] | None]],
    *,
    policy: MergePolicy = MergePolicy.FILL_IF_EMPTY,
) -> None:
    """Set fields in ``updates``, respecting the merge policy.

    ``field_map`` maps a provider metadata attribute to ``(entity_attr,
    converter)``. A field is written when the provider has a truthy value
    and ``policy.should_write`` allows it (always under ``OVERWRITE``; only
    when the entity field is empty under ``FILL_IF_EMPTY``). The
    fill-if-empty guard protects user edits on a routine re-enrichment;
    ``OVERWRITE`` (a relink / forced refresh) bypasses it so the
    newly-picked match's metadata wins over stale values.

    Args:
        updates: Mutable dict of pending ``with_updates`` kwargs.
        metadata: Provider payload to read from.
        entity: Aggregate to read current values from (duck-typed via
            ``getattr`` — Movie or Series).
        field_map: ``{provider_attr: (entity_attr, converter | None)}``.
        policy: Merge policy gating each write.
    """
    for meta_attr, (entity_attr, converter) in field_map.items():
        # No default on the provider read: ``metadata`` is always a
        # ``MediaMetadata`` with a fixed attribute set, so a mistyped map key
        # should fail loudly instead of silently skipping the field. The
        # default stays on the duck-typed ``entity`` (Movie or Series).
        meta_val = getattr(metadata, meta_attr)
        entity_val = getattr(entity, entity_attr, None)
        if meta_val and policy.should_write(entity_val):
            updates[entity_attr] = converter(meta_val) if converter is not None else meta_val


def set_provider_ids(updates: dict[str, object], metadata: MediaMetadata) -> None:
    """Always-overwrite the provider identity fields shared by movie and series.

    ``tmdb_id`` / ``imdb_id`` / ``original_title`` track the picked provider
    entry on every enrich (no fill-if-empty guard) and are written whenever
    the provider supplies them. Movie- and series-specific always-overwrite
    fields (title, year/start_year, end_year) stay in their use cases because
    their rules diverge.
    """
    if metadata.tmdb_id:
        updates["tmdb_id"] = TmdbId(metadata.tmdb_id)
    if metadata.imdb_id:
        updates["imdb_id"] = ImdbId(metadata.imdb_id)
    if metadata.original_title:
        updates["original_title"] = Title(metadata.original_title)


def set_cast_if_missing(
    updates: dict[str, object],
    metadata: MediaMetadata,
    entity: Any,
    *,
    policy: MergePolicy = MergePolicy.FILL_IF_EMPTY,
) -> None:
    """Fill-if-empty the cast, converting each ``CreditPerson`` to ``CastMember``.

    Same fill-if-empty rule as the table-driven fields, kept as its own
    helper because of the per-element DTO → value-object conversion. ``entity``
    is duck-typed (Movie or Series, both expose ``cast``).
    """
    if metadata.cast and policy.should_write(entity.cast):
        updates["cast"] = [
            CastMember(
                name=p.name,
                profile_path=p.profile_url,
                role=p.role,
                tmdb_id=p.tmdb_id,
            )
            for p in metadata.cast
        ]


def reconcile_common_fields(
    entity: Any,
    metadata: MediaMetadata,
    *,
    policy: MergePolicy,
    fill_if_empty: dict[str, tuple[str, Callable[[Any], Any] | None]],
) -> dict[str, object]:
    """Build the ``with_updates`` kwargs shared by movie and series enrich.

    Folds the provider identity fields, the ``fill_if_empty`` table, the cast,
    and the localized overlay into a fresh updates dict under ``policy``. Each
    use case then layers its type-specific always-overwrite fields (title,
    year/start_year/end_year, duration) onto the returned dict before applying
    it with ``with_updates``.

    Args:
        entity: Aggregate being enriched (Movie or Series, duck-typed).
        metadata: Provider payload.
        policy: Merge policy gating every write.
        fill_if_empty: The fill-if-empty field map for this entity type
            (``COMMON_FILL_IF_EMPTY`` plus any type-specific entries).

    Returns:
        A mutable updates dict the caller extends and passes to ``with_updates``.
    """
    updates: dict[str, object] = {}
    set_provider_ids(updates, metadata)
    set_if_missing(updates, metadata, entity, fill_if_empty, policy=policy)
    set_cast_if_missing(updates, metadata, entity, policy=policy)
    new_localized = merge_media_localized(entity.localized, metadata, policy=policy)
    if new_localized is not None:
        updates["localized"] = new_localized
    return updates


__all__ = [
    "COMMON_FILL_IF_EMPTY",
    "reconcile_common_fields",
    "set_cast_if_missing",
    "set_if_missing",
    "set_provider_ids",
]
