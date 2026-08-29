"""Build per-language metadata overrides as LocalizedMetadata value objects.

The movie/series and season/episode enrich use cases fold a provider's
per-language overrides into the entity's stored ``localized``. Both the
provider→VO translation and the merge-vs-replace decision live here so the
use cases stay declarative and no call site has to reach for the wire-dict
form (the VO owns serialization). ``MergePolicy.OVERWRITE`` (a relink)
replaces the stored overrides outright; ``FILL_IF_EMPTY`` overlays the
provider's locales on the existing ones (:meth:`LocalizedMetadata.merge`).
"""

from src.modules.media.domain.value_objects.localized_metadata import (
    LocalizedFields,
    LocalizedMetadata,
)
from src.modules.media.domain.value_objects.merge_policy import MergePolicy
from src.modules.metadata.application.ports.metadata_provider_port import (
    LocalizedTextFields,
    MediaMetadata,
)


def _resolved(
    existing: LocalizedMetadata, provider: LocalizedMetadata, *, policy: MergePolicy
) -> LocalizedMetadata | None:
    """Merge or replace, returning ``None`` when the provider has nothing.

    ``None`` lets the caller leave the entity's ``localized`` untouched.
    """
    if provider.is_empty():
        return None
    return provider if policy.overwrites else existing.merge(provider)


def merge_media_localized(
    existing: LocalizedMetadata,
    metadata: MediaMetadata,
    *,
    policy: MergePolicy = MergePolicy.FILL_IF_EMPTY,
) -> LocalizedMetadata | None:
    """Fold a movie/series provider's full per-language overrides into ``existing``.

    Maps the provider's ``localized`` records (which name artwork fields
    ``*_url``) onto :class:`LocalizedFields`, dropping locales that carry no
    usable field. Returns the merged value object, or ``None`` when the
    provider supplied no localized data.
    """
    by_locale: dict[str, LocalizedFields] = {}
    for lang, f in metadata.localized.items():
        fields = LocalizedFields(
            title=f.title or None,
            synopsis=f.synopsis or None,
            tagline=f.tagline or None,
            genres=tuple(f.genres) if f.genres else (),
            logo_path=f.logo_url or None,
            poster_path=f.poster_url or None,
            backdrop_path=f.backdrop_url or None,
        )
        if not fields.is_empty():
            by_locale[lang] = fields
    return _resolved(existing, LocalizedMetadata(by_locale), policy=policy)


def merge_text_localized(
    existing: LocalizedMetadata,
    provider_localized: dict[str, LocalizedTextFields],
    *,
    policy: MergePolicy = MergePolicy.FILL_IF_EMPTY,
) -> LocalizedMetadata | None:
    """Fold a season/episode provider's title/synopsis overrides into ``existing``.

    The lean counterpart to :func:`merge_media_localized` — seasons and
    episodes only localize ``title``/``synopsis``. Drops locales with
    neither; returns ``None`` when nothing is supplied.
    """
    by_locale: dict[str, LocalizedFields] = {}
    for lang, f in provider_localized.items():
        fields = LocalizedFields(title=f.title or None, synopsis=f.synopsis or None)
        if not fields.is_empty():
            by_locale[lang] = fields
    return _resolved(existing, LocalizedMetadata(by_locale), policy=policy)


__all__ = ["merge_media_localized", "merge_text_localized"]
