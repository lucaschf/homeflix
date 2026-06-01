"""IETF language tag value object (BCP-47 subset)."""

import re
from typing import ClassVar

from pydantic import model_validator

from src.building_blocks.domain.value_objects import StringValueObject


class LanguageTag(StringValueObject):
    """An IETF BCP-47 language tag, e.g. ``"pt"``, ``"pt-BR"``, ``"en-US"``.

    Distinct from :class:`LanguageCode`, which is the strict ISO 639-1
    two-letter form used for metadata and media tracks. The video player
    persists region-qualified tags (``"pt-BR"``) that the strict code
    rejects, so playback preferences carry this looser — but still
    validated — shape instead of a bare ``str`` that would let garbage
    like ``""`` or ``"portugues"`` round-trip to the database and out to
    the client.

    Normalization follows BCP-47 casing: the primary language subtag is
    lowercased, a two-letter region subtag is uppercased, and a
    four-letter script subtag is title-cased — so ``"PT-br"`` and
    ``"pt-BR"`` both canonicalize to ``"pt-BR"``.

    Example:
        >>> LanguageTag("pt-BR").value
        'pt-BR'
        >>> LanguageTag("EN").value
        'en'
        >>> LanguageTag("pt-br").primary_subtag
        'pt'
    """

    # Primary subtag (2-3 letters) + optional region/script/variant subtags.
    _PATTERN: ClassVar[re.Pattern[str]] = re.compile(r"^[A-Za-z]{2,3}(-[A-Za-z0-9]{1,8})*$")
    _RULE_CODE: ClassVar[str] = "SHARED.LANGUAGE_TAG.INVALID"

    @model_validator(mode="before")
    @classmethod
    def _validate(cls, value: str) -> str:
        """Validate the tag shape and return its canonical casing."""
        if not isinstance(value, str):
            raise ValueError("Language tag must be a string")

        value = value.strip()
        if not cls._PATTERN.match(value):
            raise ValueError(
                f"Invalid IETF language tag: '{value}'. Expected forms like "
                f"'pt', 'pt-BR', 'en-US' [{cls._RULE_CODE}]"
            )
        return cls._normalize(value)

    @staticmethod
    def _normalize(value: str) -> str:
        """Apply BCP-47 casing conventions to each subtag."""
        primary, *subtags = value.split("-")
        canonical = [primary.lower()]
        for sub in subtags:
            if len(sub) == 2 and sub.isalpha():
                canonical.append(sub.upper())  # region, e.g. BR / US
            elif len(sub) == 4 and sub.isalpha():
                canonical.append(sub.title())  # script, e.g. Hans
            else:
                canonical.append(sub.lower())
        return "-".join(canonical)

    @property
    def primary_subtag(self) -> str:
        """The primary language subtag, e.g. ``"pt"`` from ``"pt-BR"``.

        This is the bridge to :class:`LanguageCode`: a match against a
        media track's strict ISO 639-1 code should compare on this part,
        not the full region-qualified tag.
        """
        return self.value.split("-")[0]


__all__ = ["LanguageTag"]
