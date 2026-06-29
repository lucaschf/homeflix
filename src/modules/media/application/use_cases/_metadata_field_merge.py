"""Table-driven merge of provider metadata fields into an entity.

Both ``enrich_movie_metadata`` and ``enrich_series_metadata`` fold a bag of
provider fields onto the entity under a :class:`MergePolicy`. The
"don't-overwrite" fields all share one shape — write when the provider has
a value and the policy allows it — so the rule lives here once, driven by a
per-call field map, instead of being hand-rolled field by field in each use
case (which had drifted into two parallel implementations).
"""

from collections.abc import Callable
from typing import Any

from src.modules.media.application.ports import MediaMetadata
from src.modules.media.domain.value_objects.merge_policy import MergePolicy


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


__all__ = ["set_if_missing"]
