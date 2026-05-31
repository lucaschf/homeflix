"""Shared helper for merging per-language metadata overrides.

Both the movie and series enrich use cases need to fold the provider's
``localized`` payload into the entity's existing ``localized`` dict. The
two copies had already drifted — the movie variant carried ``tagline``
while the series variant silently dropped it — so the merge now lives in
one place and is applied uniformly to both media types.
"""

from src.modules.media.application.ports import MediaMetadata


def merge_localized_metadata(
    updates: dict[str, object],
    existing: dict[str, dict[str, object]],
    metadata: MediaMetadata,
) -> None:
    """Merge per-language overrides from ``metadata`` into ``updates``.

    Builds one entry per language with only the fields the provider
    actually returned (falsy values are dropped), then merges them over
    the entity's current ``localized`` dict. ``tagline`` is carried for
    every media type so a localized tagline from the provider is never
    discarded; entities that have no use for it simply ignore the key.

    Args:
        updates: The mutable updates dict the use case applies to the
            entity. ``"localized"`` is set here when there is anything
            to merge.
        existing: The entity's current ``localized`` mapping.
        metadata: Provider metadata carrying the ``localized`` overrides.
    """
    if not metadata.localized:
        return

    localized: dict[str, dict[str, object]] = {}
    for lang, fields in metadata.localized.items():
        candidates = {
            "title": fields.title,
            "synopsis": fields.synopsis,
            "tagline": fields.tagline,
            "genres": fields.genres or None,
            "logo_path": fields.logo_url,
        }
        loc_entry: dict[str, object] = {k: v for k, v in candidates.items() if v}
        if loc_entry:
            localized[lang] = loc_entry

    if localized:
        updates["localized"] = {**existing, **localized}


__all__ = ["merge_localized_metadata"]
