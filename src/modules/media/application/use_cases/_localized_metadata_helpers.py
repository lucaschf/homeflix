"""Shared helper for merging per-language metadata overrides.

Both the movie and series enrich use cases need to fold the provider's
``localized`` payload into the entity's existing ``localized`` dict. The
two copies had already drifted — the movie variant carried ``tagline``
while the series variant silently dropped it — so the merge now lives in
one place and is applied uniformly to both media types.
"""

from typing import Any

from src.modules.media.application.ports import LocalizedTextFields, MediaMetadata


def merge_localized_metadata(
    updates: dict[str, object],
    existing: dict[str, dict[str, object]],
    metadata: MediaMetadata,
    *,
    force: bool = False,
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
        force: When ``True`` (a relink / forced refresh) the entity's
            current ``localized`` is **replaced** by the provider's,
            dropping stale language entries left over from a wrong
            match. When ``False`` the new entries are merged over the
            existing ones (the default fill-and-update behavior).
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
            "poster_path": fields.poster_url,
            "backdrop_path": fields.backdrop_url,
        }
        loc_entry: dict[str, object] = {k: v for k, v in candidates.items() if v}
        if loc_entry:
            localized[lang] = loc_entry

    if localized:
        updates["localized"] = localized if force else {**existing, **localized}


def build_localized_text(
    provider_localized: dict[str, LocalizedTextFields],
    existing: dict[str, dict[str, Any]],
    *,
    force: bool = False,
) -> dict[str, dict[str, Any]] | None:
    """Merge per-language title/synopsis overrides for a season or episode.

    The season/episode counterpart to :func:`merge_localized_metadata` —
    seasons and episodes only localize ``title`` and ``synopsis`` (no
    artwork/genres), so this builds the lighter ``{lang: {title,
    synopsis}}`` shape. Falsy values are dropped per language.

    Args:
        provider_localized: The provider's per-language overrides.
        existing: The entity's current ``localized`` mapping.
        force: When ``True`` (a relink / forced refresh) the entity's
            ``localized`` is **replaced**, dropping stale languages;
            otherwise the new entries are merged over the existing ones.

    Returns:
        The merged ``localized`` dict to store, or ``None`` when there
        is nothing to merge (so the caller leaves the field untouched).
    """
    if not provider_localized:
        return None

    built: dict[str, dict[str, Any]] = {}
    for lang, fields in provider_localized.items():
        entry: dict[str, Any] = {
            k: v for k, v in {"title": fields.title, "synopsis": fields.synopsis}.items() if v
        }
        if entry:
            built[lang] = entry

    if not built:
        return None
    return built if force else {**existing, **built}


__all__ = ["build_localized_text", "merge_localized_metadata"]
