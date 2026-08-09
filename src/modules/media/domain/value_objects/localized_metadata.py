"""Localized metadata value object (ADR-023).

Replaces the untyped ``dict[str, dict[str, Any]]`` that the media content
entities used to carry per-language overrides. The value object owns the
single source of truth for the JSON field names (:class:`LocalizedField`)
and the localized→base fallback, and serializes to exactly the same JSON
wire shape the column already stores (so there is no migration).
"""

from enum import StrEnum
from typing import Any, ClassVar

from pydantic import ConfigDict, Field, RootModel, model_validator

from src.building_blocks.domain.value_objects import CompoundValueObject, ValueObject
from src.shared_kernel.value_objects.language_tag import LanguageTag


class LocalizedField(StrEnum):
    """Field names inside the ``localized`` JSON blob.

    Single source of truth shared by the value object and the SQL
    ``json_extract`` path builders (``_genre_helpers``), so the wire
    format and the queries that read it cannot drift apart.
    """

    TITLE = "title"
    SYNOPSIS = "synopsis"
    TAGLINE = "tagline"
    GENRES = "genres"
    LOGO_PATH = "logo_path"
    POSTER_PATH = "poster_path"
    BACKDROP_PATH = "backdrop_path"


class LocalizedFields(CompoundValueObject):
    """Per-locale override record.

    All fields are optional — the full set serves ``Movie``/``Series``
    while ``Season``/``Episode`` only ever populate ``title``/``synopsis``.
    Field names mirror :class:`LocalizedField`. ``extra="forbid"`` (inherited
    from :class:`CompoundValueObject`) makes deserialization reject unknown
    keys, per ADR-023.

    Attributes:
        title: Localized title.
        synopsis: Localized synopsis.
        tagline: Localized tagline.
        genres: Localized genre names.
        logo_path: Localized title-logo URL.
        poster_path: Localized poster URL.
        backdrop_path: Localized backdrop URL.

    Example:
        >>> LocalizedFields(title="O Espião").title
        'O Espião'
    """

    title: str | None = None
    synopsis: str | None = None
    tagline: str | None = None
    genres: tuple[str, ...] = ()
    logo_path: str | None = None
    poster_path: str | None = None
    backdrop_path: str | None = None

    def is_empty(self) -> bool:
        """Return ``True`` when no field carries a value."""
        return not (
            self.title
            or self.synopsis
            or self.tagline
            or self.genres
            or self.logo_path
            or self.poster_path
            or self.backdrop_path
        )


def _canonical(lang: str) -> str:
    """Return the canonical BCP-47 tag for *lang*, or the raw value.

    Lookups stay lenient: an unparseable tag simply misses (→ fallback),
    matching the previous raw-``dict`` behavior.
    """
    try:
        return LanguageTag(lang).value
    except Exception:
        return lang


class LocalizedMetadata(RootModel[dict[str, LocalizedFields]], ValueObject):
    """Per-language metadata overrides for a media content entity.

    Maps a canonical language tag (``"en"``, ``"pt-BR"``) to its
    :class:`LocalizedFields`. Read accessors return the localized value or
    ``None`` (the entity owns the fallback to its base fields).
    :meth:`to_serializable` reproduces the exact JSON shape stored today.

    Example:
        >>> meta = LocalizedMetadata.from_serializable({"pt-BR": {"title": "Aviões"}})
        >>> meta.text(LocalizedField.TITLE, "pt-BR")
        'Aviões'
        >>> meta.text(LocalizedField.TITLE, "fr") is None
        True
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra=None)

    root: dict[str, LocalizedFields] = Field(default_factory=dict)

    # noinspection PyNestedDecorators
    @model_validator(mode="before")
    @classmethod
    def _normalize(cls, value: Any) -> Any:
        """Canonicalize locale keys and accept dict / VO / None inputs."""
        if value is None:
            return {}
        if isinstance(value, LocalizedMetadata):
            return value.root
        if isinstance(value, dict):
            return {
                _canonical(str(key)): fields
                for key, fields in value.items()
                if fields not in (None, {})
            }
        return value

    def _lookup(self, lang: str) -> LocalizedFields | None:
        """Return the override record for *lang*, if any."""
        return self.root.get(_canonical(lang))

    def text(self, field: LocalizedField, lang: str) -> str | None:
        """Return the localized scalar for *field*/*lang*, or ``None``.

        Not for :attr:`LocalizedField.GENRES` — use :meth:`genres`.
        """
        fields = self._lookup(lang)
        if fields is None:
            return None
        value = getattr(fields, field.value)
        return str(value) if value else None

    def genres(self, lang: str) -> tuple[str, ...] | None:
        """Return localized genres for *lang*, or ``None`` when absent."""
        fields = self._lookup(lang)
        if fields is None:
            return None
        return fields.genres or None

    def is_empty(self) -> bool:
        """Return ``True`` when there are no localized overrides."""
        return not self.root

    def merge(self, other: "LocalizedMetadata") -> "LocalizedMetadata":
        """Return a copy with *other*'s locales overlaid on this one.

        Locale-level (not field-level) override: a locale present in
        *other* replaces this object's entry for that locale entirely,
        while locales only in ``self`` are kept. Mirrors the previous
        ``{**existing, **provider}`` merge — used by the enrich write
        path to fold provider overrides over the stored ones.
        """
        return LocalizedMetadata({**self.root, **other.root})

    def to_serializable(self) -> dict[str, dict[str, Any]]:
        """Serialize to the stored JSON shape (only non-falsy fields).

        Reproduces the legacy wire format exactly: per locale, only the
        fields the provider actually supplied, ``genres`` as a list, and
        locales with no surviving field omitted.
        """
        out: dict[str, dict[str, Any]] = {}
        for lang, fields in self.root.items():
            entry: dict[str, Any] = {}
            for field in LocalizedField:
                if field is LocalizedField.GENRES:
                    if fields.genres:
                        entry[field.value] = list(fields.genres)
                else:
                    value = getattr(fields, field.value)
                    if value:
                        entry[field.value] = value
            if entry:
                out[lang] = entry
        return out

    @classmethod
    def from_serializable(cls, raw: dict[str, dict[str, Any]] | None) -> "LocalizedMetadata":
        """Build from the stored JSON dict (``None`` → empty)."""
        # Pydantic coerces the raw nested dict into LocalizedFields at the
        # RootModel boundary; mypy can't follow that coercion.
        return cls(raw or {})  # type: ignore[arg-type]


__all__ = ["LocalizedField", "LocalizedFields", "LocalizedMetadata"]
